import os
import uuid
import shutil
import docker
from contextlib import asynccontextmanager
import kubernetes

from fastapi import FastAPI
from git import Repo
from pydantic import BaseModel

BASE_PATH = "./temp"

docker_client = docker.from_env()

kubernetes.config.load_kube_config()
k8s_core_api_client = kubernetes.client.CoreV1Api()
k8s_apps_api_client = kubernetes.client.AppsV1Api()
k8s_networking_api_client = kubernetes.client.NetworkingV1Api()


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
    return new_image_tag


async def create_k8s_deployment(namespace_name, image_tag, deployment_name):
    namespace = kubernetes.client.V1Namespace(
        api_version="v1",
        kind="Namespace",
        metadata=kubernetes.client.V1ObjectMeta(name=namespace_name),
    )
    k8s_core_api_client.create_namespace(namespace)

    print("created namespace")

    # TODO jaki port???

    container = kubernetes.client.V1Container(
        name="container",
        image=image_tag,
        ports=[kubernetes.client.V1ContainerPort(container_port=8080)]
    )

    # Create and configure a spec section
    template = kubernetes.client.V1PodTemplateSpec(
        metadata=kubernetes.client.V1ObjectMeta(labels={"app": "container"}),
        spec=kubernetes.client.V1PodSpec(containers=[container]),
    )

    # Create the specification of deployment
    spec = kubernetes.client.V1DeploymentSpec(
        replicas=1, template=template, selector={
            "matchLabels":
                {"app": "container"}})

    # Instantiate the deployment object
    deployment = kubernetes.client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=kubernetes.client.V1ObjectMeta(name=deployment_name),
        spec=spec,
    )

    k8s_apps_api_client.create_namespaced_deployment(namespace_name, deployment)

    print("created deployment")

    # create service
    service = kubernetes.client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=kubernetes.client.V1ObjectMeta(name=deployment_name),
        spec=kubernetes.client.V1ServiceSpec(
            selector={"app": "container"},
            ports=[kubernetes.client.V1ServicePort(
                port=8080, target_port=8080)]
        )
    )
    k8s_core_api_client.create_namespaced_service(namespace_name, service)

    print("created service")

    # create ingress
    ingress = kubernetes.client.V1Ingress(
        api_version="networking.k8s.io/v1",
        kind="Ingress",
        metadata=kubernetes.client.V1ObjectMeta(name=deployment_name),
        spec=kubernetes.client.V1IngressSpec(
            rules=[kubernetes.client.V1IngressRule(
                host=f"{deployment_name}.rasztabiga.me",
                http=kubernetes.client.V1HTTPIngressRuleValue(
                    paths=[kubernetes.client.V1HTTPIngressPath(
                        path="/",
                        path_type="Prefix",
                        backend=kubernetes.client.V1IngressBackend(
                            service=kubernetes.client.V1IngressServiceBackend(
                                port=kubernetes.client.V1ServiceBackendPort(
                                    number=8080
                                ),
                                name=deployment_name
                            )
                        )
                    )]
                )
            )]
        )
    )
    k8s_networking_api_client.create_namespaced_ingress(namespace_name, ingress)

    print("created ingress")

    # get url
    return f"https://{deployment_name}.rasztabiga.me"


async def deploy(repo_url):
    repo_name = repo_url.split("/")[-1].split(".")[0]
    user_id = uuid.uuid4()
    deployment_id = f"{repo_name}-{user_id}"
    repo_path = f"{BASE_PATH}/{deployment_id}"

    await clone_repo(repo_url, repo_path)
    await check_dockerfile(repo_path)
    image_tag = await build_image(repo_path, deployment_id)
    print(image_tag)

    new_image_tag = await push_image(image_tag)
    print("pushed")

    url = await create_k8s_deployment(deployment_id, new_image_tag, deployment_id)

    # push docker image to cluster?
    # create k8s deployment + service + ingress config giles
    # apply k8s config files
    # return url

    return url


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.post("/deployments")
async def create_deployment(request: CreateDeploymentRequest):
    url = await deploy(request.repo_url)
    return {"url": url}
