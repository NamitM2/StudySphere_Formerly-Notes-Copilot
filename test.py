# test.py
# Path: test.py
import base64, json
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJuYW1pdG1laHRhMUBnbWFpbC5jb20iLCJlbWFpbCI6Ik5hbWl0bWVodGExQGdtYWlsLmNvbSIsImlhdCI6MTc1OTY0NTg0Mn0.bYY03r0R1W16tupn_syNZg6H08g8-IRpgvvVB1qA1Rg"
hdr = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
print("alg =", hdr["alg"])
