import argparse
import socket
import requests


def local_ip():
    """
    Tries to get the local IP address of the computer using sockets
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Google's public DNS server
        local_ip_address, _ = s.getsockname()
        s.close()
        return local_ip_address
    except Exception as e:
        print(f"Error getting local IP: {e}")
        return None

def public_ip():
    """
    Gets the public IP address using an external service
    """
    try:
        response = requests.get("https://ipinfo.io/ip", timeout=5)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        return response.text.strip()
    except requests.exceptions.RequestException as e:
        print(f"Error getting public IP: {e}")
        return None

def main():
    """
    Main function to parse command-line arguments and run the program
    """
    parser = argparse.ArgumentParser(description="Get information about your IP address or ping a URL.")

    # Create a mutually exclusive group for public and all options
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--public", action="store_true", help="Shows your public IP address.")
    group.add_argument("--all", action="store_true", help="Shows both public and local IP addresses.")

    args = parser.parse_args()
    if args.public:
        pub_ip = public_ip()
        if pub_ip:
            print(f"Public: {pub_ip}")
    elif args.all:
        loc_ip = local_ip()
        pub_ip = public_ip()
        if loc_ip:
            print(f"Local: {loc_ip}")
        if pub_ip:
            print(f"Public: {pub_ip}")
    else:
        # If no arguments are provided, show local and public IP
        loc_ip = local_ip()
        if loc_ip:
            print(f"Local: {loc_ip}")


if __name__ == "__main__":
    main()
