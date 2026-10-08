if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    from photocheck.app import main
    raise SystemExit(main())
