#! python

def main():
    from alora.observatory.observatory import Observatory
    o = Observatory()
    o.connect()
    print("Attempting opening sequence.")
    o.open()

if __name__ == "__main__":
    main()