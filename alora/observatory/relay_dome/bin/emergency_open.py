#! python

def main():
    import os
    from alora.observatory import Observatory

    o = Observatory()
    print("DOME EMERGENCY OPEN")
    confirm = input("Confirm that the telescope is in a park position by typing \"the telescope is parked\": ")
    if confirm == "the telescope is parked":
        o.dome._open()
    else:
        print("Confirmation failed.")

if __name__ == "__main__":
    main()