import os
import time

import docker
import logging

from dotenv import load_dotenv
from openai import OpenAI
from git import Repo

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI()
model = "gpt-4o-mini"
temperature = 0.2

docker_client = docker.from_env()


def prepare_working_directory(tmp_dir):
    logger.info("Preparing working directory...")

    # clear dir
    os.system(f"rm -rf {tmp_dir}")

    # create dir
    os.makedirs(tmp_dir, exist_ok=True)


def clone_repo(repo_url, tmp_dir):
    logger.info("Cloning repository...")

    # clone repo
    Repo.clone_from(repo_url, tmp_dir)


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

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant, that given repository files structure (only some part of it) will help to identify the most important files to generate a Dockerfile to build a valid docker image that can be run to run the app of repository. Respond only with the file names, in the same format as provided, ignore formatting markers.",
            },
            {"role": "user", "content": tree_str},
        ],
        temperature=temperature,
    )

    content = completion.choices[0].message.content

    # get files from response and trim (strip)
    files = list(map(lambda x: x.strip(), content.split("\n")))

    # ignore .jar and Dockerfile files (unsupported)
    ignored_files = [".jar", "Dockerfile"]
    files = [file for file in files if not any(ignored_file in file for ignored_file in ignored_files)]

    return files


def get_files_content(files, tmp_dir):
    logger.info("Preparing files content...")

    # get files content
    files_content = {}
    for file in files:
        with open(tmp_dir + file, "r") as f:
            files_content[file] = f.read()

    return files_content


def get_dockerfile(tree_str, files_content):
    logger.info("Generating Dockerfile...")

    prompt = f"""
    {tree_str}
    
    {files_content}
    """

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant, that given repository files structure (only some part of it) and content of the most important files will help to generate a Dockerfile to build a valid docker image that can be run to run the app of repository. Use latest base image versions and best practises, implement all security measures and expose all necessary ports. Respond only with the content of the Dockerfile, ignore formatting markers.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )

    content = completion.choices[0].message.content

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

def build_docker_image(tmp_dir, repo_name):
    logger.info("Building Docker image...")

    # build docker image
    image_tag = repo_name.lower()
    image, logs = docker_client.images.build(path=tmp_dir, tag=image_tag)

    return image

def run_docker_image(image, dockerfile):
    logger.info("Running Docker image...")

    exposed_ports = get_exposed_ports(dockerfile)

    # run docker image, expose ports according to Dockerfile
    ports = {}
    for port in exposed_ports:
        ports[port] = None

    container = docker_client.containers.run(image, detach=True, ports=ports)

    time.sleep(5)  # wait for container to start

    container.reload()

    return container

def do_magic(repo_url):
    # TODO rewrite to oop

    logger.info("Starting with repo_url: %s", repo_url)

    repo_name = repo_url.split("/")[-1].replace(".git", "")

    tmp_dir = f"./tmp/{repo_name}"

    prepare_working_directory(tmp_dir)
    clone_repo(repo_url, tmp_dir)

    tree_str = prepare_repo_tree_as_string(tmp_dir)

    important_files = get_important_files(tree_str)
    files_content = get_files_content(important_files, tmp_dir)

    dockerfile = get_dockerfile(tree_str, files_content)

    write_dockerfile(tmp_dir, dockerfile)


    image = build_docker_image(tmp_dir, repo_name)

    container = run_docker_image(image, dockerfile)

    container_ports = container.attrs["NetworkSettings"]["Ports"]

    for port in container_ports:
        host_port = container_ports[port][0]["HostPort"]
        logger.info("Container running on port %s", host_port)

    logger.info("DONE")


def main():
    logging.basicConfig(level=logging.INFO)

    # repo_url = "https://github.com/BartlomiejRasztabiga/run-example.git"
    # repo_url = "git@bitbucket.org:symmetricalai/employee-management.git"
    repo_url = "git@github.com:BartlomiejRasztabiga/FO23Z.git"
    do_magic(repo_url)


if __name__ == "__main__":
    main()
