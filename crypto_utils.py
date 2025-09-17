import base64
from typing import Tuple, Optional
import json

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.Cipher import AES
from base64 import b64decode


class DeterministicHMACDRBG:
    """Deterministic byte stream generator (HMAC-DRBG-like) for RSA generation from a seed.
    This is NOT a standards-compliant DRBG; it is sufficient to deterministically derive RSA keys
    from a stable mnemonic seed within this application context.
    """

    def __init__(self, seed: bytes):
        self._key = seed
        self._counter = 0

    def read(self, nbytes: int) -> bytes:
        out = bytearray()
        while len(out) < nbytes:
            msg = self._counter.to_bytes(8, "big") + b"/drbg"
            digest = SHA256.new(self._key + msg).digest()
            out.extend(digest)
            self._counter += 1
        return bytes(out[:nbytes])


def derive_rsa_keypair_from_mnemonic(mnemonic: str, bits: int = 2048) -> Tuple[str, str]:
    """Derive a deterministic RSA keypair (PEM strings) from a mnemonic using HKDF -> DRBG.
    Returns (private_pem, public_pem).
    """
    salt = b"cellvoyager-rsa-salt"
    info = b"cellvoyager-rsa-info"
    seed = HKDF(master=mnemonic.encode("utf-8"), key_len=32, salt=salt, hashmod=SHA256, context=info)
    drbg = DeterministicHMACDRBG(seed)
    key = RSA.generate(bits, randfunc=drbg.read)
    priv_pem = key.export_key(format="PEM").decode("utf-8")
    pub_pem = key.publickey().export_key(format="PEM").decode("utf-8")
    return priv_pem, pub_pem


def decrypt_base64_oaep(encrypted_b64: str, private_pem: str) -> Optional[str]:
	"""Decrypt base64 RSA-OAEP(SHA256) ciphertext to a UTF-8 string. Returns None on failure."""
	try:
		if not encrypted_b64:
			return None
		ciphertext = base64.b64decode(encrypted_b64)
		key = RSA.import_key(private_pem)
		cipher = PKCS1_OAEP.new(key, hashAlgo=SHA256)
		plaintext = cipher.decrypt(ciphertext)
		return plaintext.decode("utf-8")
	except Exception:
		return None


def decrypt_envelope_or_oaep(data: str, private_pem: str) -> Optional[str]:
	"""Decrypts either a hybrid envelope (RSA-OAEP + AES-GCM) or legacy base64 RSA-OAEP.

	Hybrid JSON format:
	{
	  "alg": "RSA-OAEP+AES-GCM",
	  "ek": "<base64 RSA-encrypted AES key>",
	  "iv": "<base64 12-byte IV>",
	  "ct": "<base64 ciphertext||tag>"
	}
	"""
	if not data:
		return None
	try:
		obj = json.loads(data)
		if not isinstance(obj, dict):
			return decrypt_base64_oaep(data, private_pem)
		if obj.get("alg") != "RSA-OAEP+AES-GCM":
			return decrypt_base64_oaep(data, private_pem)
		ek_b64 = obj.get("ek"); iv_b64 = obj.get("iv"); ct_b64 = obj.get("ct")
		if not (ek_b64 and iv_b64 and ct_b64):
			return None
		# RSA decrypt AES key
		key = RSA.import_key(private_pem)
		cipher_rsa = PKCS1_OAEP.new(key, hashAlgo=SHA256)
		aes_key = cipher_rsa.decrypt(b64decode(ek_b64))
		iv = b64decode(iv_b64)
		ct = b64decode(ct_b64)
		if len(ct) < 16:
			return None
		ciphertext, tag = ct[:-16], ct[-16:]
		cipher_aes = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
		pt = cipher_aes.decrypt_and_verify(ciphertext, tag)
		return pt.decode("utf-8")
	except Exception:
		# Fallback to direct OAEP base64
		return decrypt_base64_oaep(data, private_pem)
