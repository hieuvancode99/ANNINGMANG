# BÁO CÁO TÓM TẮT ĐỒ ÁN
## Tích hợp Học sâu (Deep Learning) vào Bộ điều khiển mạng SDN để phát hiện và ngăn chặn tấn công DDoS theo thời gian thực

---

### 1. MỤC TIÊU ĐỀ TÀI
Biến một mạng máy tính thụ động thành một hệ thống "mạng thông minh", có khả năng tự động giám sát (Monitoring), chẩn đoán (AI Detection) và ngăn chặn (Mitigation) các đợt tấn công Từ chối dịch vụ phân tán (DDoS) mà không cần sự can thiệp thủ công của con người.

---

### 2. KIẾN TRÚC HỆ THỐNG
Hệ thống được thiết kế theo đúng chuẩn 3 lớp của kiến trúc SDN (Software-Defined Networking):

* **Lớp Dữ liệu (Data Plane - Mininet):** 
  Bao gồm các Máy chủ/Người dùng (Hosts) và Bộ chuyển mạch (Open vSwitch). Đây là nơi lưu lượng mạng thực tế chạy qua. Các Switch hoàn toàn không có khả năng tự tư duy, chúng hoạt động dựa trên các luật (Flow rules) được đẩy xuống từ Controller.
  
* **Lớp Điều khiển (Control Plane - Ryu Controller):** 
  Đóng vai trò là "Bộ não trung tâm". Controller kết nối với Switch qua giao thức OpenFlow. Nhiệm vụ của nó là học địa chỉ MAC, định tuyến gói tin và thu thập các số liệu thống kê (Flow Stats) từ mạng.

* **Lớp Ứng dụng (Application Plane - AI Module):** 
  Module Học Sâu (Deep Learning) được cấy trực tiếp lên Controller. Khối này bao gồm 3 mô hình AI tiên tiến (LSTM, Transformer, Autoencoder) làm nhiệm vụ phân tích các luồng mạng để tìm ra dấu hiệu bất thường của tấn công DDoS.

---

### 3. LUỒNG HOẠT ĐỘNG (WORKFLOW)
Hệ thống phòng thủ hoạt động theo một vòng lặp khép kín cực kỳ chặt chẽ gồm 4 bước:

1. **Thu thập số liệu (Polling):** Cứ mỗi 5 giây, Controller lại gửi yêu cầu `OFPFlowStatsRequest` tới Switch để lấy báo cáo lưu lượng (Packet count, Byte count) của các luồng mạng.
2. **Trích xuất đặc trưng (Feature Extraction):** Controller tính toán sự chênh lệch (Delta) về số lượng gói tin và dung lượng giữa 2 chu kỳ gần nhất để xác định "vận tốc" của luồng dữ liệu. Các thông số này được gom thành một vector đặc trưng (6 features).
3. **AI Suy luận (Inference):** Vector đặc trưng được bơm vào mô hình Học Sâu (Ví dụ: LSTM). Thuật toán LSTM theo dõi dữ liệu theo trục thời gian (Time-series với Window Size = 10). Nếu tốc độ gói tin tăng vọt bất thường (đặc trưng của SYN Flood), AI sẽ kết luận đây là luồng tấn công DDoS với độ tin cậy (Confidence) cực cao.
4. **Tự động ngăn chặn (Mitigation):** Ngay khi AI phát ra cảnh báo, Controller lập tức tạo một **Luật chặn (DROP Rule)** và đẩy xuống Switch thông qua bản tin `OFPFlowMod`. Mọi gói tin từ kẻ tấn công sẽ bị rớt thẳng ở tầng Switch trong 60 giây tiếp theo, bảo vệ an toàn tuyệt đối cho Máy chủ đích.

---

### 4. ĐIỂM SÁNG GIÁ TRỊ VÀ ĐÓNG GÓP CỦA ĐỒ ÁN
Dự án mang tính ứng dụng thực tiễn rất cao với 3 điểm nhấn công nghệ:

* **Xử lý Thời gian thực (Real-time Detection):** Dựa trên kết quả Benchmark, quá trình từ lúc lấy số liệu tới lúc AI xử lý xong chỉ tốn trung bình **0.5 tới 2 mili-giây** (tuỳ mô hình). Đây là tốc độ cực kỳ lý tưởng, giúp ngăn chặn DDoS tức thời mà không gây ra độ trễ (latency) cho lưu lượng mạng hợp lệ.
* **Mô hình Khép kín (End-to-End Mitigation):** Hệ thống không chỉ đưa ra cảnh báo thụ động trên màn hình mà còn **chủ động can thiệp** vào phần cứng mạng (Switch) để triệt tiêu nguồn tấn công. Điều này chứng minh ứng dụng thiết thực của công nghệ SDN.
* **Công nghệ "Thay Nóng" qua REST API (Hot-Swapping):** Hệ thống được thiết kế theo chuẩn kiến trúc công nghiệp (Enterprise Architecture). Quản trị viên có thể chuyển đổi linh hoạt giữa các mô hình AI (từ LSTM sang Transformer hoặc Autoencoder) chỉ bằng 1 câu lệnh API mà **không làm gián đoạn đường truyền mạng** đang hoạt động.
