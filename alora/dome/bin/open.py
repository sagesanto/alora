#! python

def main():
    import os
    import dotenv

    from alora.dome import Dome

    dotenv.load_dotenv()

    dome = Dome(os.getenv("DOME_ADDR"),os.getenv("DOME_USERNAME"),os.getenv("DOME_PASSWORD"))
    dome.open()

if __name__ == "__main__":
    main()