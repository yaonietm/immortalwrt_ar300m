import socket
import threading
import time
import paho.mqtt.client as mqtt
import os

# ========= 配置 =========
MQTT_HOST = "bemfa.com"
MQTT_PORT = 9501
CLIENT_ID = ""

TARGET_IP = "192.168.4.2"
TARGET_PORT = 14301
LOG_FILE = "/var/log/mqtt.log"
MAX_SIZE = 100 * 1024
MQTT_TOPIC_SUB = "door001"
MQTT_TOPIC_SUB15 = "shiwu001"
TEMP_SUBMIT_TOPIC = "router004"
TEMP_INTERVAL = 3  # 上报时间

# 260524 开门失效，新增udp返回数据判断
UDP_BIND_IP = "0.0.0.0"
UDP_PORT = 14301


def udp_monitor():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_BIND_IP, UDP_PORT))
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [UDP监听启动]，端口{UDP_PORT}")
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            hex_str = data.hex()
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [UDP数据]来自 {addr} | HEX: {hex_str}")
        except Exception as e:
            print("UDP监听异常：", e)
            time.sleep(1)


# 开门数据
HEX_CMD = "08ff010800000000000000000000000053470000760000000000000000002800760000000101010032000100000000004af0630231000100000000000000000032aaf0a000010000"

# UDP socket
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
temp_thread_running = False


# 获取路由器CPU温度函数
def get_router_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_raw = int(f.read().strip())
        temp = round(temp_raw / 1000, 1)
        return f"#{temp}#0"
    except:
        return f"#-99#0"


# 定时上报线程
def temp_report_task(mqtt_client):
    while True:
        temp_val = get_router_temp()
        mqtt_client.publish(TEMP_SUBMIT_TOPIC, temp_val)
        # print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [温度上报] {TEMP_SUBMIT_TOPIC} => {temp_val}")
        time.sleep(TEMP_INTERVAL)


# 检查日志
def check_log_size():
    try:
        if os.path.exists(LOG_FILE):
            size = os.path.getsize(LOG_FILE)
            print(f"日志文件大小为：{size}")
            if size > MAX_SIZE:
                print("[LOG] 日志超过60KB，已清空")
                with open(LOG_FILE, "w") as f:
                    f.truncate(0)
    except Exception as e:
        print("[LOG] 检查日志失败:", e)


# ========= MQTT回调 =========
def on_connect(client, userdata, flags, rc):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}[MQTT] 已连接 rc={rc}")
    client.subscribe(MQTT_TOPIC_SUB)
    client.subscribe(MQTT_TOPIC_SUB15)


def on_message(client, userdata, msg):
    payload = msg.payload.decode().strip().upper()
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [MQTT] 收到: {payload}------")

    if payload == "ON":
        if msg.topic == MQTT_TOPIC_SUB:
            threading.Thread(target=trigger, args=(client, TARGET_IP, TARGET_PORT, HEX_CMD, MQTT_TOPIC_SUB),
                             daemon=True).start()
        if msg.topic == MQTT_TOPIC_SUB15:
            threading.Thread(target=trigger, args=(client, "192.168.15.2", TARGET_PORT, HEX_CMD, MQTT_TOPIC_SUB15),
                             daemon=True).start()


# ========= 核心动作 =========
def trigger(client, ip, port, hex_cmd1, topic):
    try:
        # 发送UDP
        data = bytes.fromhex(hex_cmd1)
        udp_sock.sendto(data, (ip, port))

        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{topic}] 已发送开门指令给({ip},{port})")

        # 延迟恢复OFF
        time.sleep(2)
        client.publish(topic, "off")  # 对应主题回复off

    except Exception as e:
        print(f"[{topic}] 错误：", e)


# ========= 主程序 =========
def main():
    threading.Thread(target=udp_monitor, daemon=True).start()
    global temp_thread_running
    # client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    # client = mqtt.Client(client_id=CLIENT_ID, clean_session=True, protocol=mqtt.MQTTv311)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=CLIENT_ID, clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message

    client.reconnect_delay_set(min_delay=1, max_delay=60)

    while True:
        try:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ====[SYS脚本开始启动]==== 开始连接MQTT...")
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            if temp_thread_running == False:
                threading.Thread(target=temp_report_task, args=(client,), daemon=True).start()  # 启动上报
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [温度上报已启动]，上报间隔为{TEMP_INTERVAL}s")
                temp_thread_running = True

            client.loop_forever()
        except Exception as e:
            print("[SYS] 异常，重试:", e)
            time.sleep(5)


if __name__ == "__main__":
    check_log_size()
    main()
