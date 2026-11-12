FROM golang:1.22-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
RUN CGO_ENABLED=0 go build -o /out/node ./cmd/node && CGO_ENABLED=0 go build -o /out/loadgen ./cmd/loadgen

FROM alpine:3.20
RUN apk add --no-cache iproute2
COPY --from=build /out/node /usr/local/bin/node
COPY --from=build /out/loadgen /usr/local/bin/loadgen
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["node"]
