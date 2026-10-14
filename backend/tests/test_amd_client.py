from app.services.amd_token_factory import AMDTokenFactory


def main():
    print("Connecting to AMD Token Factory...")

    amd = AMDTokenFactory()

    response = amd.chat(
        "You are an industrial factory inspection assistant. "
        "Explain three common warning signs of machine failure."
    )

    print("\nAMD MODEL RESPONSE:\n")
    print(response)


if __name__ == "__main__":
    main()