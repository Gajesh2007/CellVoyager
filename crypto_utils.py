import base64
from typing import Tuple, Optional
import json

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.Cipher import AES
from base64 import b64decode



def derive_rsa_keypair_from_mnemonic(mnemonic: str, bits: int = 2048) -> Tuple[str, str]:
	"""Derive a deterministic RSA keypair (PEM strings) from a mnemonic using HKDF-derived entropy.

	Returns (private_pem, public_pem).
	"""
	salt = b"cellvoyager-rsa-salt"
	info = b"cellvoyager-rsa-info"
	# Estimate the number of bytes needed for RSA key generation entropy
	# 256 bytes is sufficient for 2048-bit keys
	entropy = HKDF(master=mnemonic.encode("utf-8"), key_len=256, salt=salt, hashmod=SHA256, context=info)
	entropy_offset = [0]  # mutable offset
	def randfunc(n):
		result = entropy[entropy_offset[0]:entropy_offset[0]+n]
		entropy_offset[0] += n
		# If we run out of entropy, re-derive with a different info/context
		if len(result) < n:
			raise ValueError("Not enough entropy for RSA key generation")
		return result
	key = RSA.generate(bits, randfunc=randfunc)
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
