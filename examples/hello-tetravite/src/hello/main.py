import sys,json
def main():
    obj=json.load(sys.stdin)
    print(json.dumps({"greeting":"Hello, " + obj["name"]}))
