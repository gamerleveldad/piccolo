import asyncio
import socket
import json
import os
import logging
import aiomqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
UDP_PORT = 50222

def mps_to_mph(mps_speed: float) -> float: 
    return round(mps_speed * 2.23694, 1)

async def listen_and_bridge():
    # Setup UDP Socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", UDP_PORT))
    sock.setblocking(False)
    loop = asyncio.get_event_loop()
    
    logging.info(f"Connecting to MQTT broker at {MQTT_BROKER}...")
    
    # Connect to MQTT and listen to UDP continuously
    while True:
        try:
            async with aiomqtt.Client(MQTT_BROKER) as client:
                logging.info(f"Tempest Bridge Online. Listening on UDP {UDP_PORT} and publishing to weather/tempest/live")
                while True:
                    data, _ = await loop.sock_recvfrom(sock, 1024)
                    raw_json = json.loads(data.decode('utf-8'))
                    
                    packet_type = raw_json.get("type")
                    payload = None
                    
                    # Normalize the Tempest data
                    if packet_type == "rapid_wind":
                        ob = raw_json.get("ob", [])
                        if ob: payload = {"update_type": "rapid_wind", "wind_speed_mph": mps_to_mph(ob[1]), "wind_direction_deg": ob[2]}
                    
                    elif packet_type == "evt_strike":
                        evt = raw_json.get("evt", [])
                        if evt: payload = {"update_type": "lightning_strike", "distance_miles": round(float(evt[1]) * 0.621371, 1), "energy": evt[2], "timestamp": raw_json.get("timestamp")}
                    
                    elif packet_type == "obs_st":
                        obs = raw_json.get("obs", [[]])[0]
                        if obs: 
                            # Extract Tempest Indices
                            temp_c = float(obs[7])
                            rh = float(obs[8])
                            lux = int(obs[9])
                            temp_f = round((temp_c * 9/5) + 32, 1)
                            
                            payload = {
                                "update_type": "sensor_snapshot",
                                "temp_f": temp_f,
                                "humidity": rh,
                                "lux": lux,
                                "wind_gust_mph": mps_to_mph(obs[3]),
                                "wind_direction_deg": obs[4],
                                "rain_rate_in_hr": round((obs[12] / 25.4) * 60, 2)
                                # Note: index 18 is local daily rain accumulation, but only exists on newer firmware
                            }
                    
                    # Publish to MQTT
                    if payload:
                        await client.publish("weather/tempest/live", payload=json.dumps(payload))
        
        except Exception as e:
            logging.error(f"MQTT Connection Error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(listen_and_bridge())