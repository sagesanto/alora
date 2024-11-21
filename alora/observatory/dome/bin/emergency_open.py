#! python

def main():
    import os
    import dotenv

    from alora.observatory import Dome

    dotenv.load_dotenv()

    dome = Dome(os.getenv("DOME_ADDR"),os.getenv("DOME_USERNAME"),os.getenv("DOME_PASSWORD"))
    print("DOME EMERGENCY OPEN")
    confirm = input("Confirm that the telescope is in a park position by typing \"the telescope is parked\": ")
    if confirm == "the telescope is parked":
        dome._open()
    else:
        print("Confirmation failed.")

if __name__ == "__main__":
    main()