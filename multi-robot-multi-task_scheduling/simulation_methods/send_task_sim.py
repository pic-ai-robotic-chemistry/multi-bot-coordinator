import json
import requests
import time


def load_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data


if __name__ == "__main__":
    json_file_path = "./examples/5_experiments.json"
    
    post_url = "http://127.0.0.1:5051/scheduling_test"

    while True:
        try:
            data = load_json_file(json_file_path)
            response = requests.post(post_url, json=data)
            print("\nReceive Response...")
        except Exception as e:
            print("An error occurred:", e)
        time.sleep(2)
