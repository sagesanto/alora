#! python

def main():
    from alora.observatory.observatory import Observatory
    o = Observatory()
    o.connect()
    print("Taking some images")
    print(o.camera.take_dataset(10,1,"L",r"D:\tests\camera_control_test","im2"))

if __name__ == "__main__":
    main()