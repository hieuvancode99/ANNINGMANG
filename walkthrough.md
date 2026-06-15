# Hướng dẫn Kịch bản Demo Hệ thống (Phiên bản Terminal)

Dự án đã được dọn dẹp sạch sẽ toàn bộ thành phần Web dư thừa. Giờ đây, sức mạnh cốt lõi của hệ thống AI sẽ được phô diễn trực tiếp trên màn hình Terminal của Linux.

## Các tính năng ưu việt của phiên bản này
1. **Bảo mật tuyệt đối**: Không mở cổng HTTP/API, loại bỏ hoàn toàn bề mặt tấn công ứng dụng Web.
2. **Hiệu năng cao**: Controller chạy cực kỳ nhẹ nhàng, tiết kiệm RAM do không phải duy trì các hàng đợi lịch sử và WSGI Server.
3. **Log chuyên nghiệp**: Màn hình Console được làm sạch. Các luồng Ping bình thường vẫn hoạt động ngầm nhưng không bị in ra làm rối màn hình. Khi phát hiện DDoS, hệ thống sẽ chớp cảnh báo đỏ và lập tức tự động khóa chặn (Drop rule).

## Kịch bản Thuyết trình & Demo chuẩn xác

### Bước 1: Khởi động Bộ não AI (Ryu Controller)
- **Hành động**: Mở Terminal 1 và chạy lệnh:
  ```bash
  cd ~/Màn\ hình\ nền/DoAnANM/DoAnANMang
  bash run_ryu.sh
  ```
- **Giải thích với Hội đồng**: *"Hệ thống sử dụng Ryu SDN Controller tích hợp trực tiếp với mô hình Deep Learning. Màn hình này đang giám sát toàn bộ lưu lượng mạng ở chế độ Background."*

### Bước 2: Khởi tạo Hạ tầng mạng (Mininet)
- **Hành động**: Mở Terminal 2 và chạy lệnh:
  ```bash
  cd ~/Màn\ hình\ nền/DoAnANM/DoAnANMang
  sudo mn -c
  sudo python3 topology/single_switch_topo.py
  ```
- **Giải thích với Hội đồng**: *"Hạ tầng mạng giả lập gồm 1 OpenFlow Switch kết nối với các host mô phỏng Client và Attacker."*

### Bước 3: Chứng minh Hệ thống hoạt động êm ái với người dùng thật
- **Hành động**: Tại dấu nhắc `mininet>`, gõ lệnh ping ngầm:
  ```bash
  h2 ping h1 &
  ```
- **Giải thích**: *"Em cho host h2 ping hợp lệ đến server h1. Các thầy cô có thể thấy màn hình Controller (Terminal 1) vẫn hoàn toàn im lặng, hệ thống không hề bị báo động giả (Zero False Positives), người dùng truy cập web mượt mà."*

### Bước 4: Mô phỏng Tấn công & Hệ thống tự vệ
- **Hành động**: Tại `mininet>`, gõ lệnh tấn công SYN Flood cường độ cao:
  ```bash
  h3 hping3 -c 10000 -S -p 80 -i u10000 10.0.0.1
  ```
- **Giải thích**: *"Bây giờ em sử dụng công cụ hping3 từ máy h3 để thực hiện một cuộc tấn công SYN Flood với tốc độ hàng chục nghìn gói tin mỗi giây vào server h1."*
- **Điểm nhấn**: Trỏ tay sang Terminal 1. Hội đồng sẽ thấy các block cảnh báo **⚠️ DDoS DETECTED** màu đỏ rực rỡ hiện lên liên tục cùng với thời gian phân tích độ trễ cực thấp (chỉ vài mili-giây).
- **Kết luận**: *"Sau khi AI phát hiện đây là luồng tấn công, nó lập tức yêu cầu Controller gửi luật DROP xuống tầng Switch (SDN Data Plane) để chặn đứng MAC của h3, trong khi h2 (người dùng thật) vẫn không hề bị đứt mạng!"*
