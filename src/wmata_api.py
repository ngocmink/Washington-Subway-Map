import requests

class WmataAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.wmata.com"

    def get_realtime_prediction(self, station_code):
        """Lấy thời gian tàu sắp đến tại một ga cụ thể"""
        endpoint = f"{self.base_url}/StationPrediction.svc/json/GetPrediction/{station_code}"
        headers = {"api_key": self.api_key}
        
        try:
            response = requests.get(endpoint, headers=headers)
            data = response.json()
            # Lấy số phút của chuyến tàu gần nhất
            if data['Trains']:
                prediction = data['Trains'][0]['Min']
                return 0 if prediction in ['ARR', 'BRD', ''] else int(prediction)
            return 999 # Không có tàu
        except Exception as e:
            print(f"Lỗi gọi API: {e}")
            return 0