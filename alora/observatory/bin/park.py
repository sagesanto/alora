#! python

def main():
    from alora.observatory.observatory import Observatory
    o = Observatory()
    o.connect()
    print("Parking...")
    o.telescope.park()
    print("Parked.")

if __name__ == "__main__":
    main()