# The CA used in the tests

This certificate authority was generated with OpenSSL 3.3.2.

## CA generation

```
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 -out ca.crt
```

## Server certificate

```
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr
```
