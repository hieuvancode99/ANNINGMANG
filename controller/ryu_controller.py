"""
ryu_controller.py — Ryu SDN Controller tích hợp AI DDoS Detection

Chức năng:
    1. L2 Learning Switch  — học MAC address, forward/flood packet
    2. Flow Stats Polling  — định kỳ gửi OFPFlowStatsRequest
    3. Feature Extraction  — tính Delta features từ flow stats
    4. AI Inference        — hot-swap LSTM / Transformer / Autoencoder
    5. Mitigation          — tự động install drop rule khi phát hiện DDoS

Cách chạy (trên máy Linux có Ryu):
    ryu-manager controller/ryu_controller.py --observe-links

Sau đó chạy Mininet:
    sudo python topology/single_switch_topo.py
"""

import os
import sys
import time
import logging
import threading

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp
from ryu.lib import hub
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from webob import Response
import json

# Thêm thư mục gốc vào path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import (
    POLLING_CYCLE, ACTIVE_MODEL,
    AUTO_DROP, DROP_RULE_PRIORITY, DROP_RULE_TIMEOUT,
    LOG_LEVEL, LOG_FILE
)
from controller.feature_extractor import FeatureExtractor
from controller.inference_engine import InferenceEngine

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("RyuController")


# ============================================================
# REST API (WSGI)
# ============================================================
class ModelSwapController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(ModelSwapController, self).__init__(req, link, data, **config)
        self.sdn_app = data['sdn_app']

    @route('model', '/api/model', methods=['PUT'])
    def swap_model(self, req, **kwargs):
        try:
            body = json.loads(req.body)
            new_model = body.get('model', '').lower()
            if new_model in ['lstm', 'transformer', 'autoencoder']:
                # Gửi lệnh đổi model tới controller
                self.sdn_app.swap_model(new_model)
                return Response(status=200, json_body={'status': 'ok', 'model': new_model})
            else:
                return Response(status=400, json_body={'error': 'Invalid model: must be lstm, transformer, or autoencoder'})
        except Exception as e:
            return Response(status=500, json_body={'error': str(e)})


# ============================================================
# CONTROLLER
# ============================================================
class SDNDDoSController(app_manager.RyuApp):
    """
    Ryu Controller với AI-powered DDoS detection.

    Architecture:
        Ryu Event Thread  →  feature_extractor  →  data_queue
                                                          ↓
                                                  inference_worker (thread)
                                                          ↓
                                                   result_queue
                                                          ↓
                                                  alert_handler (thread)
                                                          ↓
                                              install_drop_rule / log
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SDNDDoSController, self).__init__(*args, **kwargs)

        # Đăng ký REST API
        wsgi = kwargs['wsgi']
        wsgi.register(ModelSwapController, {'sdn_app': self})

        # L2 MAC learning table: {dpid: {mac: port}}
        self.mac_to_port = {}

        # Theo dõi các datapath đã kết nối
        self.datapaths = {}

        # Lưu match info của flow để install drop rule
        # {flow_id: (datapath, match)}
        self.flow_match_cache = {}

        # ---- Feature Extractor ----
        self.extractor = FeatureExtractor(model_name=ACTIVE_MODEL)

        # ---- Inference Engine ----
        self.engine = InferenceEngine(
            model_name=ACTIVE_MODEL,
            on_alert=self._on_ddos_alert
        )
        self.engine.start()

        # ---- Poll thread (Ryu greenlet) ----
        self._poll_thread = hub.spawn(self._poll_loop)

        logger.info(
            f"[Controller] SDNDDoSController started | "
            f"model={ACTIVE_MODEL} | poll_cycle={POLLING_CYCLE}s"
        )

    # ===========================================================
    # EVENT: Switch connects
    # ===========================================================
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Gửi table-miss flow entry khi switch kết nối."""
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser

        self.datapaths[datapath.id] = datapath
        self.mac_to_port.setdefault(datapath.id, {})

        # Table-miss entry: gửi tất cả packet không match về controller
        match   = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)

        logger.info(f"[Controller] Switch connected: dpid={datapath.id:#x}")

    # ===========================================================
    # EVENT: Packet In — L2 Learning Switch
    # ===========================================================
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Xử lý packet-in: học MAC address và forward."""
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        in_port  = msg.match["in_port"]
        dpid     = datapath.id

        pkt  = packet.Packet(msg.data)
        eth  = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        dst = eth.dst
        src = eth.src

        # Học MAC
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # Quyết định output port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install flow rule nếu không flood
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self._add_flow(datapath, priority=1, match=match,
                               actions=actions, buffer_id=msg.buffer_id)
                return
            else:
                self._add_flow(datapath, priority=1, match=match, actions=actions)

        # Gửi packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    # ===========================================================
    # EVENT: Flow Stats Reply
    # ===========================================================
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """Nhận flow stats → extract features → submit vào inference queue."""
        body     = ev.msg.body
        datapath = ev.msg.datapath
        dpid     = datapath.id

        if not body:
            return

        # Cập nhật cache match info (để install drop rule sau này)
        for stat in body:
            fid = self.extractor._state.flow_id(dpid, stat)
            self.flow_match_cache[fid] = (datapath, stat.match)

        # Trích xuất features
        ready_flows = self.extractor.process_stats_reply(dpid, body)

        # Submit vào inference queue
        for flow_id, features in ready_flows:
            self.engine.submit(flow_id, features)

        logger.debug(
            f"[Controller] dpid={dpid:#x} | "
            f"stats={len(body)} flows | "
            f"submitted={len(ready_flows)} for inference"
        )

    # ===========================================================
    # POLLING LOOP (Ryu greenlet)
    # ===========================================================
    def _poll_loop(self):
        """Định kỳ gửi OFPFlowStatsRequest đến tất cả switches."""
        while True:
            hub.sleep(POLLING_CYCLE)
            self._request_flow_stats()

    def _request_flow_stats(self):
        """Gửi OFPFlowStatsRequest đến tất cả switches đang kết nối."""
        for dpid, datapath in list(self.datapaths.items()):
            ofproto = datapath.ofproto
            parser  = datapath.ofproto_parser

            req = parser.OFPFlowStatsRequest(datapath)
            datapath.send_msg(req)
            logger.debug(f"[Controller] FlowStatsRequest → dpid={dpid:#x}")

    # ===========================================================
    # ALERT CALLBACK
    # ===========================================================
    def _on_ddos_alert(self, flow_id: str, result: dict):
        """
        Callback được gọi bởi InferenceEngine khi phát hiện DDoS.
        Chạy trong AlertHandler thread.
        """
        logger.warning(
            f"\n{'='*60}\n"
            f"  ⚠️  DDoS DETECTED!\n"
            f"  Flow ID:    {flow_id}\n"
            f"  Model:      {result['model_name']}\n"
            f"  Confidence: {result['confidence']:.4f}\n"
            f"  Latency:    {result['infer_latency_ms']:.2f} ms\n"
            f"{'='*60}"
        )

        if AUTO_DROP:
            self._install_drop_rule(flow_id)

    def _install_drop_rule(self, flow_id: str):
        """Cài đặt flow rule DROP để block traffic DDoS."""
        if flow_id not in self.flow_match_cache:
            logger.warning(f"[Controller] No match info for flow {flow_id}, cannot drop.")
            return

        datapath, match = self.flow_match_cache[flow_id]
        parser   = datapath.ofproto_parser

        # actions=[] → DROP (không có action nào = drop)
        self._add_flow(
            datapath,
            priority=DROP_RULE_PRIORITY,
            match=match,
            actions=[],
            hard_timeout=DROP_RULE_TIMEOUT
        )
        logger.info(
            f"[Controller] DROP rule installed: "
            f"dpid={datapath.id:#x} | timeout={DROP_RULE_TIMEOUT}s"
        )

    # ===========================================================
    # HOT-SWAP MODEL (API)
    # ===========================================================
    def swap_model(self, new_model_name: str):
        """
        Hot-swap model tại runtime.
        Gọi từ REST API hoặc CLI.

        Args:
            new_model_name: "lstm" | "transformer" | "autoencoder"
        """
        self.engine.swap_model(new_model_name)
        self.extractor.set_model(new_model_name)
        logger.info(f"[Controller] Model swapped to '{new_model_name}'")

    # ===========================================================
    # HELPER: Add Flow Entry
    # ===========================================================
    def _add_flow(self, datapath, priority, match, actions,
                  buffer_id=None, hard_timeout=0, idle_timeout=0):
        """Helper để cài đặt flow entry vào switch."""
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions
        )]

        kwargs = dict(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            hard_timeout=hard_timeout,
            idle_timeout=idle_timeout,
        )
        if buffer_id is not None and buffer_id != ofproto.OFP_NO_BUFFER:
            kwargs["buffer_id"] = buffer_id

        mod = parser.OFPFlowMod(**kwargs)
        datapath.send_msg(mod)

    # ===========================================================
    # STATS (cho benchmark)
    # ===========================================================
    def get_stats(self) -> dict:
        """Trả về thống kê hệ thống."""
        return {
            "active_model":    self.engine._model_name,
            "connected_dpids": list(self.datapaths.keys()),
            "latency":         self.engine.get_latency_stats(),
            "extractor":       self.extractor.get_stats(),
            "queue_data":      self.engine.data_queue.qsize(),
            "queue_result":    self.engine.result_queue.qsize(),
        }
