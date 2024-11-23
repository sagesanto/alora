#! python

def main():
    from alora.observatory.observatory import Observatory
    o = Observatory()
    o.connect()
    print("Finding home...")
    o.telescope.home()
    print("Found home.")

if __name__ == "__main__":
    main()