# The CA used in the tests

This certificate authority was generated with OpenSSL 3.3.2.

## CA generation

```
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -not_after 20990101000000Z -out ca.crt
```

## Server certificate

```
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -out server.crt -not_after 20990101000000Z
```
