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


async def build_image(repo_path, repo_name):
    image, build_logs = docker_client.images.build(
        path=repo_path, tag=repo_name, rm=True, pull=True
    )
    print(image)
    print(build_logs)


async def deploy(repo_url):
    repo_name = repo_url.split("/")[-1].split(".")[0]
    user_id = uuid.uuid4()
    repo_path = f"{BASE_PATH}/{repo_name}-{user_id}"

    await clone_repo(repo_url, repo_path)
    await check_dockerfile(repo_path)
    await build_image(repo_path, repo_name)
    # build docker image
    # push docker image to cluster?
    # create k8s deployment + service + ingress config giles
    # apply k8s config files
    # return url

    pass


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.post("/deployments")
async def create_deployment(request: CreateDeploymentRequest):
    await deploy(request.repo_url)
