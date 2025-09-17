// Client-side RSA-OAEP(SHA-256) encryption helpers

export function pemToArrayBuffer(pem: string): ArrayBuffer {
	const cleaned = pem
		.replace(/-----BEGIN PUBLIC KEY-----/g, "")
		.replace(/-----END PUBLIC KEY-----/g, "")
		.replace(/\s+/g, "");
	const binary = atob(cleaned);
	const bytes = new Uint8Array(binary.length);
	for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
	return bytes.buffer;
}

export async function importRsaPublicKeySpki(pem: string): Promise<CryptoKey> {
	const spki = pemToArrayBuffer(pem);
	return crypto.subtle.importKey(
		"spki",
		spki,
		{ name: "RSA-OAEP", hash: "SHA-256" },
		true,
		["encrypt"]
	);
}

export async function rsaOaepEncryptToBase64(pemPublicKey: string, plaintext: string): Promise<string> {
	const key = await importRsaPublicKeySpki(pemPublicKey);
	const enc = new TextEncoder().encode(plaintext);
	const ct = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, key, enc);
	const b = new Uint8Array(ct);
	let str = "";
	for (let i = 0; i < b.length; i++) str += String.fromCharCode(b[i]);
	return btoa(str);
}

function ab2b64(buf: ArrayBuffer): string {
	const b = new Uint8Array(buf);
	let s = "";
	for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
	return btoa(s);
}

export async function encryptUrlEnvelope(pemPublicKey: string, url: string): Promise<string> {
	// Hybrid: RSA-OAEP encrypts AES key, AES-GCM encrypts URL
	const rsa = await importRsaPublicKeySpki(pemPublicKey);
	const aesKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
	const aesRaw = await crypto.subtle.exportKey("raw", aesKey);
	const iv = crypto.getRandomValues(new Uint8Array(12));
	const ctBuf = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, aesKey, new TextEncoder().encode(url));
	const ekBuf = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, rsa, aesRaw);
	const payload = {
		alg: "RSA-OAEP+AES-GCM",
		ek: ab2b64(ekBuf),
		iv: ab2b64(iv.buffer),
		ct: ab2b64(ctBuf),
	};
	return JSON.stringify(payload);
}


