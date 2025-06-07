import base64
import hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import argparse

def get_hash(request):
    """Generate SHA-256 hash of input data and encode as base64"""
    hash_obj = hashlib.sha256(request.encode())
    return base64.b64encode(hash_obj.digest()).decode()

def sign_data(data, private_key_pem):
    """Sign data using RSA private key with SHA-256"""
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
        )
        
        signature = private_key.sign(
            data.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        return base64.b64encode(signature).decode()
    except Exception as e:
        print(f"Signing Error: {e}")
        return None

def run(signature_input):
    """Process input: hash and sign it"""
    # Get the hash
    hash_value = get_hash(signature_input)
    print(f"Hash: {hash_value}")
    
    # Private key (same as in the JS version)
    private_key = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCPJ4/16KEOVaao
2VDen9oSS+lh272ohJINqtU93db5qdQMUGldlJrYvkuBY9Xo0iEeYO/eL/IAyPOp
WVLqufE9jmp03U5uvsJn9VxPw9dCDJo9r5jcmq0XZtLN6SE1adfWlpTiSxvSIJY9
CeE8YiwS+wN3gbESBmPLzs1jew6iwjkF2nla70fYZ27gt44CqzUw/qC2IG+sIsha
8pvCiTms7OQYWQuF1g21FQJtm4JTAPF59pv8H6SGE6i81Y6QCchts8XwCj+JZ/JK
2KBuH26Z2CkDZSSvLWYdiqW+wEBqgFAWEfhIj0dpCP5wsiYe1aGwpIIytXdym9kN
hE7tg6x7AgMBAAECggEACbB3/ivRNDWtkpx8QfKYNt3RfZtQcnwKoLHb6L8/rOVc
TLsSmVAUzQUlpNaGOici27oG8kcqKPhxBEOJ/l44iwiSgbd1oWmi90NfDKe+RaJc
Zul1k2pFZfdCice074xq8gN+L0o90f1SU0OnGEhddalsxNAlP97pLqMgOWgGXRNm
EHpKCxlp4QbhUA+CuzGeAq/OtMjEZOHUJC511pwnffluCbx0LD5Cs66L5eV2MIMj
s/GEpfxALv05YdUhfraAD7IM8plUk7IWWmV4Cjjiv7CQzdfZ8RgRm14TOICWCl+K
q9BVsC/UkQIPQYNhQ9OHhze9cHC4lnU4jry7CmiUyQKBgQDBW1zM3A96U8qgmIB5
jXgpw6++01HF76ccqjUp7NW4YD0D3zjmaLfxIf5FypCK31ONPwDutWgE8+0T+wqW
jtIs+/icm8O6TAR4+kR+/vkGWQwBRG9Hju1JOgtAdtYCrFASzqzJxIMGrYkPq584
J4HMUhw2v3yYcMmS7NRWanVmQwKBgQC9iIRH1VknHAOeeKVDh3vJyA+UJJJJQyj1
aqmSSLO4bRjBu2uKhXH4VboQ+fSPUm+AnqdY1YMCXorc38/WDOT/A8OvVkeCulM+
kx76stJIyUSNVWf48jv5kCa51++2Mw9LAN798zgPjVKwzWfMR4Ux8amue5c6c2ZQ
P7g++FQpaQKBgGfDgd+mUOASy3C3pmqU0uGG1G+RtBaG76Vgajtfj6nsa5ICXuS3
Wc8bsPr/I+aCxrHMF9ICpBnUVWwdkqcNahkd92MD7Fuzo8rQc6W7ayRO8TRU52r9
drWPYq5rl5nDow0UwIFe5fnVcvJn5YAbI3rkraNry497J5GjaqgdZXdFAoGAU+cf
R/12Xg3UvE6EOoS7k/PwkZAvAies9helwZBVnwsMrpadYND6RwkMOX+td9Tyb2nM
g1LhkCbyKh0aEJPcu9eaxP/Y4FJDj6vpRunqlTYkFrz8LgRt8GiT/ClPgMTRvE5C
aQFGi/vv4zzK+m+e0yE8EHW92K5FWLkcgyPDfiECgYEAjn8BMNT0fDiqtqmm4mhq
Yj9xLgFbLtfVX0QY6MpPjaKzGIuTe26hdxPuJwwdeUduoxEWJYrPVLjaheTQ/nSP
8jbqzaZaV+IWstI/Gy0PkcgF57fbjebnwBkLA6MQvuSmRDXqXTHbOY8Hx4AvEnRa
t6dk2ozSDhyz6DAkFhtaoHU=
-----END PRIVATE KEY-----"""
    
    # Sign the data
    signature = sign_data(signature_input, private_key)
    print(f"Signature: {signature}")
    
    return {
        "hash": hash_value,
        "signature": signature
    }

def main():
    parser = argparse.ArgumentParser(description='Hash and sign input data')
    parser.add_argument('input', nargs='?', help='Input string to hash and sign')
    args = parser.parse_args()
    
    if args.input:
        result = run(args.input)
        print("\nResult:")
        print(f"Hash: {result['hash']}")
        print(f"Signature: {result['signature']}")
    else:
        # Interactive mode if no command line argument
        while True:
            user_input = input("\nEnter string to hash and sign (or 'exit' to quit): ")
            if user_input.lower() == 'exit':
                break
            
            result = run(user_input)
            print("\nResult:")
            print(f"Hash: {result['hash']}")
            print(f"Signature: {result['signature']}")

if __name__ == "__main__":
    main()