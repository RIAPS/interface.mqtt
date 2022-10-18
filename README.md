# interface.mqtt

[Gabor's Instructions](https://github.com/RIAPS/example.mqnr/blob/accff50375c904a468dbd4c22b7c07f26b8e62fe/MQTTNodeRed/README.md)

Steps I took:
1. ```wget https://www.flashmq.org/wp-content/uploads/2021/10/flashmq-repo.gpg```
2. `sudo mv flash-repo.gpg /etc/apt/keyrings`
3. ```echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/flashmq-repo.gpg] http://repo.flashmq.org/apt focal main" | sudo tee /etc/apt/sources.list.d/flashmq.list > /dev/null```
4. add `allow_anonymous true` to `/etc/flashmq/flashmq.conf`
5. `sudo systemctl restart flashmq.service` so that `allow_anonymous` takes effect.
6. ```sudo python3 -m pip install paho-mqtt```
