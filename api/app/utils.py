"""Utils"""

import json

# from functools import wraps
from faunadb import query as q

# from itsdangerous import URLSafeTimedSerializer
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from authlib.oidc.core import CodeIDToken
from authlib.jose import jwt

# from authlib.jose.errors import InvalidClaimError
from six.moves.urllib.request import urlopen
from bottle import response, request
from . import AUTH0_DOMAIN
from . import faunadb_client

# Misc


def jsonify(*args, **kwargs):
    """Response helper"""
    if args and kwargs:
        raise TypeError("jsonify() behavior undefined when passed both args and kwargs")
    if len(args) == 1:
        data = args[0]
    else:
        data = args or kwargs

    if "status" in data:
        response.status = data["status"]
        # Remove element from response
        del data["status"]

    response.content_type = "application/json"
    return json.dumps(data)


# Auth


def get_pubkey(auth0_domain):
    """Get public key from a given Auth0 domain"""

    jsonurl = urlopen(f"{auth0_domain}/.well-known/jwks.json")
    jwks = json.loads(jsonurl.read())
    x5c = jwks["keys"][0]["x5c"][0]
    cert_str = f"-----BEGIN CERTIFICATE-----\n{x5c}\n-----END CERTIFICATE-----\n"
    cert_obj = load_pem_x509_certificate(cert_str.encode("utf-8"), default_backend())
    return cert_obj.public_key()


def decode_token(token):
    """Decodes and validates an auth0 token"""

    if token is None:
        raise "Token is missing"

    public_key = get_pubkey(AUTH0_DOMAIN)
    claims_options = {
        "iss": {"essential": True, "values": [f"{AUTH0_DOMAIN}/"]},
        "sub": {"essential": False},
    }
    decoded = jwt.decode(
        token, public_key, claims_cls=CodeIDToken, claims_options=claims_options
    )
    decoded.validate()
    return decoded


# def requires_auth(func):
#     """Auth decorator"""

#     @wraps(func)
#     def decorated(*args, **kwargs):
#         # 1. get token from the header
#         token = request.get_cookie("token")

#         # 2. decode token
#         try:
#             decode_token(token)
#         # 3. catch exceptions
#         except InvalidClaimError as error:
#             print("Invalid claim error", error)
#             return jsonify(
#                 status_code=401,
#                 message={
#                     "code": "invalid_claims",
#                     "description": "Incorrect claims, please check the issuer",
#                 },
#             )
#         return func(*args, **kwargs)

#     return decorated


def get_token():
    """Get token from the cookie headers"""
    token = request.get_cookie("token")
    return decode_token(token)


# Database


# def generate_timed_signed_token(token):
#     """Add docstring"""
#     serializer = URLSafeTimedSerializer(SECRET)
#     return serializer.dumps(token, salt=SALT)


# def decode_timed_signed_token(token, expiration=3600):
#     """Decodes and verifies a given timed signed token"""
#     serializer = URLSafeTimedSerializer(SECRET)
#     return serializer.loads(token, salt=SALT, max_age=expiration)


# def get_signed_token():
#     """Retreieves token from the request cookie and decodes it"""
#     token = request.get_cookie("token")
#     print("token from get_signed_token", token)
#     return decode_timed_signed_token(token)


def find_ref(index, match_values):
    """Find user reference"""
    return q.select(["ref"], q.get(q.match(q.index(index), match_values)))


def exchange_jwt_for_secret(auth0_jwt):
    """
    Generates a Fauna token from a given Auth0 JWT

    - Decodes the token
    - Extracts the `auth0_id` from the decoded object
    - Searches for the user in the database
    - Generates a token based on the user reference
    - Returns the token
    """

    decoded = decode_token(auth0_jwt)
    auth0_id = decoded["sub"].replace("auth0|", "")

    secret = faunadb_client.query(
        q.let(
            {
                "userToken": q.let(
                    {"userRef": find_ref("users_by_auth0_id", auth0_id)},
                    q.do(q.create(q.tokens(), {"instance": q.var("userRef")})),
                )
            },
            q.do(q.select(["secret"], q.var("userToken"))),
        )
    )

    return secret
