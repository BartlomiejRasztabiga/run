#!/usr/bin/env sh

if [[ -z "${OPENAI_API_KEY}" ]]; then
  echo "OPENAI_API_KEY is not set"
  exit 1
fi

# upgrade packages
sudo apt update
sudo apt dist-upgrade -y

# install microk8s
sudo snap install microk8s --classic
microk8s status --wait-ready

# enable addons
microk8s enable registry
microk8s enable ingress

# install docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo groupadd docker
sudo usermod -aG docker $USER
newgrp docker

# clone worker repo
git clone git@github.com:BartlomiejRasztabiga/run.git
cd run
echo "OPENAI_API_KEY=$OPENAI_API_KEY" > .env
echo "REGISTRY_URL=localhost:32000" >> .env