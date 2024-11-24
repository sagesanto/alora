#! python

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=str, help="The images to solve.")
    args = parser.parse_args()
    from alora.observatory.observatory import Observatory
    o = Observatory()

    o.connect()
    print("Solving...")
    if len(args.images) == 1:
        print(o.camera.solve(args.images[0]))
    if len(args.images) > 1:
        print(o.camera.batch_solve(args.images))
    print("Done.")

if __name__ == "__main__":
    main()