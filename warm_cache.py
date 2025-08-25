import sys, requests

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000"

def warm(url: str):
    print("warm:", url)
    r = requests.get(f"{base}/read", params={"url": url}, stream=True, timeout=180)
    for _ in r.iter_content(65536):
        pass
    print("done:", r.status_code)

def main():
    with open("urls.txt", "r", encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if not url:
                continue
            warm(url)

if __name__ == "__main__":
    main()


