import logging
import os
import shutil
import time

import docker
from dotenv import load_dotenv
from git import Repo

from models import get_model

load_dotenv()

logger = logging.getLogger(__name__)

docker_client = docker.from_env()

# TODO typ k8s servicu?
# TODO fix prompt formatting

model = get_model("gpt-4o-mini")
print(model)


def prepare_working_directory(tmp_dir):
    logger.info("Preparing working directory...")

    # clear dir
    shutil.rmtree(tmp_dir, ignore_errors=True)

    # create dir
    os.makedirs(tmp_dir, exist_ok=True)


def clone_repo(repo_url, tmp_dir):
    logger.info("Cloning repository...")

    # clone repo
    Repo.clone_from(repo_url, tmp_dir)

    # TODO remove confusing files
    confusing_files = ["Dockerfile", "k8s.yaml"]
    for file in confusing_files:
        if os.path.exists(tmp_dir + "/" + file):
            os.remove(tmp_dir + "/" + file)


def prepare_repo_tree_as_string(tmp_dir):
    logger.info("Preparing tree...")

    # get tree ignoring .git
    dir_tree = tree(tmp_dir, level=1, ignore=[".git"])

    # tree to string, ignoring .git
    tree_str = tree_to_str(dir_tree, trim_dir=tmp_dir)

    return tree_str


def tree(some_dir, level, ignore):
    some_dir = some_dir.rstrip(os.path.sep)
    assert os.path.isdir(some_dir)
    num_sep = some_dir.count(os.path.sep)
    for root, dirs, files in os.walk(some_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]
        for i in ignore:
            if i in dirs:
                dirs.remove(i)


def tree_to_str(tree, trim_dir=None):
    tree_str = ""
    for root, dirs, files in tree:
        if trim_dir:
            root = root.replace(trim_dir, "")
        for file in files:
            tree_str += f"{root}/{file}\n"
    return tree_str


def get_important_files(tree_str):
    logger.info("Finding important files...")

    content = model.ask_model("get_important_files", tree_str)

    # get files from response and trim (strip)
    files = list(map(lambda x: x.strip(), content.split("\n")))

    # remove empty strings
    files = list(filter(None, files))

    # ignore .jar and Dockerfile files (unsupported)
    ignored_files = [".jar", "Dockerfile", "k8s.yaml"]
    files = [file for file in files if not any(ignored_file in file for ignored_file in ignored_files)]

    return files


def get_files_content(files, tmp_dir):
    logger.info("Preparing files content...")

    # get files content
    files_content = {}
    for file in files:
        with open(tmp_dir + "/" + file, "r") as f:
            files_content[file] = f.read()

    return files_content


def get_dockerfile(tree_str, files_content):
    logger.info("Generating Dockerfile...")

    prompt = f"""
    {tree_str}
    
    {files_content}
    """

    content = model.ask_model("get_dockerfile", prompt)

    return content


def write_dockerfile(tmp_dir, content):
    logger.info("Writing Dockerfile...")

    # write Dockerfile to tmp
    with open(tmp_dir + "/Dockerfile", "w") as f:
        f.write(content)


def get_exposed_ports(dockerfile):
    exposed_ports = []
    for line in dockerfile.split("\n"):
        if "EXPOSE" in line:
            exposed_ports = line.split(" ")[1:]
    return exposed_ports


def build_docker_image(tmp_dir, image_tag):
    logger.info("Building Docker image...")

    # build docker image
    image, logs = docker_client.images.build(path=tmp_dir, tag=image_tag, forcerm=True, pull=False)

    # push to registry
    docker_client.images.push(image_tag)

    return image


def get_k8s_config(tmp_dir, tree_str, files_content, dockerfile, image_tag):
    # TODO
    logger.info("Preparing Kubernetes config...")

    # create files to apply
    # this files will be used to create k8s deployment, service and ingress

    prompt = f"""
    {tree_str}
    
    {files_content}
    
    {dockerfile}
    
    Image tag: {image_tag}
    """

    k8s_config = model.ask_model("get_k8s_config", prompt)

    # write to file
    with open(tmp_dir + "/k8s.yaml", "w") as f:
        f.write(k8s_config)


def run_docker_image(image, exposed_ports):
    logger.info("Running Docker image...")

    # run docker image, expose ports according to Dockerfile
    ports = {}
    for port in exposed_ports:
        ports[port + '/tcp'] = None

    container = docker_client.containers.run(image, detach=True, ports=ports)

    time.sleep(5)  # wait for container to start

    container.reload()

    return container


def do_magic(repo_url):
    # TODO rewrite to oop

    logger.info("Starting with repo_url: %s", repo_url)

    repo_name = repo_url.split("/")[-1].replace(".git", "")
    registry = os.getenv("REGISTRY_URL")

    tmp_dir = f"./tmp/{repo_name}"

    prepare_working_directory(tmp_dir)
    clone_repo(repo_url, tmp_dir)

    tree_str = prepare_repo_tree_as_string(tmp_dir)

    important_files = get_important_files(tree_str)
    files_content = get_files_content(important_files, tmp_dir)

    dockerfile = get_dockerfile(tree_str, files_content)

    write_dockerfile(tmp_dir, dockerfile)

    image_tag = f"{registry}/{repo_name.lower()}:latest"
    image = build_docker_image(tmp_dir, image_tag)

    exposed_ports = get_exposed_ports(dockerfile)

    # container = run_docker_image(image, exposed_ports)

    get_k8s_config(tmp_dir, tree_str, files_content, dockerfile, image_tag)

    logger.info("DONE")


def main():
    logging.basicConfig(level=logging.INFO)

    # repo_url = "https://github.com/BartlomiejRasztabiga/run-example.git"
    repo_url = "https://github.com/BartlomiejRasztabiga/FO23Z.git"
    do_magic(repo_url)


if __name__ == "__main__":
    main()
