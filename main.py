import os
import uuid
import shutil
import docker
from contextlib import asynccontextmanager

from fastapi import FastAPI
from git import Repo
from pydantic import BaseModel

BASE_PATH = "./temp"

docker_client = docker.from_env()


class CreateDeploymentRequest(BaseModel):
    repo_url: str


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await setup_worker()
    yield


app = FastAPI(lifespan=lifespan)


async def setup_worker():
    # if os.path.exists(BASE_PATH):
    #     shutil.rmtree(BASE_PATH)

    os.makedirs(BASE_PATH, exist_ok=True)


async def clone_repo(repo_url, repo_path):
    try:
        Repo.clone_from(repo_url, repo_path, depth=1)
    except Exception as e:
        print(e)


async def check_dockerfile(repo_path):
    dockerfile_path = f"{repo_path}/Dockerfile"
    if not os.path.exists(dockerfile_path):
        raise Exception("Dockerfile not found")


async def build_image(repo_path, image_name):
    image, build_logs = docker_client.images.build(
        path=repo_path, tag=image_name, rm=True, pull=True
    )

    return image.tags[0]


async def push_image(image_tag):
    prefix = "localhost:32000"
    new_image_tag = f"{prefix}/{image_tag}"
    print(new_image_tag)
    docker_client.images.get(image_tag).tag(new_image_tag)
    docker_client.images.push(new_image_tag)


async def deploy(repo_url):
    repo_name = repo_url.split("/")[-1].split(".")[0]
    user_id = uuid.uuid4()
    image_name = f"{repo_name}-{user_id}"
    repo_path = f"{BASE_PATH}/{image_name}"

    await clone_repo(repo_url, repo_path)
    await check_dockerfile(repo_path)
    image_tag = await build_image(repo_path, image_name)
    print(image_tag)

    await push_image(image_tag)
    print("pushed")


    # push docker image to cluster?
    # create k8s deployment + service + ingress config giles
    # apply k8s config files
    # return url

    return image_tag


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.post("/deployments")
async def create_deployment(request: CreateDeploymentRequest):
    image_tag = await deploy(request.repo_url)
    return {"image_tag": image_tag}
