#!/usr/bin/env bash
export HOME=~
set -eux pipefail
mkdir -p ~/.bitcoin
cat > ~/.bitcoin/bitcoin.conf <<EOF
regtest=1
txindex=1
printtoconsole=1
rpcuser=doggman
rpcpassword=donkey
rpcallowip=127.0.0.1
zmqpubrawblock=tcp://127.0.0.1:28332
zmqpubrawtx=tcp://127.0.0.1:28333
fallbackfee=0.0002
[regtest]
rpcbind=0.0.0.0
rpcport=18554
EOF
rm -rf ~/.bitcoin/regtest
screen -S bitcoind -X quit || true
screen -S bitcoind -m -d bitcoind -regtest
sleep 6
addr=$(bitcoin-cli getnewaddress)
bitcoin-cli generatetoaddress 150 $addr > /dev/null
