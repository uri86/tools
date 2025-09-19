import argparse
import requests
import psutil
import ipaddress


def local_ips():
    """
    Get private and public local IPv4 addresses across all NICs.
    Returns a dict: {"private": [(nic, ip), ...], "public": [(nic, ip), ...]}
    """
    results = []

    try:
        addrs = psutil.net_if_addrs()
        for nic, info in addrs.items():
            for addr in info:
                if addr.family.name == "AF_INET":  # IPv4 only
                    ip = addr.address
                    results.append((nic, ip))
    except Exception as e:
        print(f"Error getting local IPs: {e}")

    return results

def print_local_ips(ips: list | tuple):
    print("Local:")
    for nic, ip in ips:
        print(f"  {ip} ({nic})")


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
    parser = argparse.ArgumentParser(description="Get information about your IP addresses.")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--public", action="store_true", help="Shows your public IP address.")
    group.add_argument("--all", action="store_true", help="Shows both public and local IP addresses.")

    args = parser.parse_args()

    if args.public:
        pub_ip = public_ip()
        if pub_ip:
            print(f"Public:\n  {pub_ip}")

    elif args.all:
        ips = local_ips()
        pub_ip = public_ip()

        print_local_ips (ips)
        if pub_ip:
            print(f"Public:\n  {pub_ip}")

    else:
        print_local_ips(local_ips())


if __name__ == "__main__":
    main()
