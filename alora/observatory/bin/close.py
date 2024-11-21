#! python

def main():
    from alora.observatory.observatory import Observatory
    o = Observatory()
    o.connect()
    print("Attempting closing sequence.")
    o.close()

if __name__ == "__main__":
    main()