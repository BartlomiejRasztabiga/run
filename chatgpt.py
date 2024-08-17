import os
import docker

from dotenv import load_dotenv
from openai import OpenAI
from git import Repo

def tree(some_dir, level):
    some_dir = some_dir.rstrip(os.path.sep)
    assert os.path.isdir(some_dir)
    num_sep = some_dir.count(os.path.sep)
    for root, dirs, files in os.walk(some_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]

load_dotenv()

client = OpenAI()

# model = "gpt-4o-mini"
model = "gpt-4o"
temperature = 0.2

# repo_url = "https://github.com/BartlomiejRasztabiga/run-example.git"
repo_url = "git@bitbucket.org:symmetricalai/employee-management.git"
repo_name = repo_url.split("/")[-1].replace(".git", "")

tmp_dir = f"./tmp/{repo_name}"

print("Preparing working directory...")

# clear dir
os.system(f"rm -rf {tmp_dir}")

# create dir
os.makedirs(tmp_dir, exist_ok=True)

print("Cloning repository...")

# clone repo
repo = Repo.clone_from(repo_url, tmp_dir)

print("Preparing tree...")

# get tree ignoring .git
tree = tree(tmp_dir, level=1)

# tree to string, ignoring .git
tree_str = ""
for root, dirs, files in tree:
    root_without_tmp = root.replace(tmp_dir, "")
    for file in files:
        if ".git" not in root:
            tree_str += f"{root_without_tmp}/{file}\n"

# print(tree_str)

print("Finding important files...")

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

print("Preparing files content...")

# get files from response and trim (strip)
files = list(map(lambda x: x.strip(), content.split("\n")))

# ignore .jar and Dockerfile files (unsupported)
ignored_files = [".jar", "Dockerfile"]
files = [file for file in files if not any(ignored_file in file for ignored_file in ignored_files)]

# get files content
files_content = {}
for file in files:
    with open(tmp_dir + file, "r") as f:
        files_content[file] = f.read()

print("Generating Dockerfile...")

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

print("Writing Dockerfile...")

# write Dockerfile to tmp
with open(tmp_dir + "/Dockerfile", "w") as f:
    f.write(content)

exposed_ports = []
for line in content.split("\n"):
    if "EXPOSE" in line:
        exposed_ports = line.split(" ")[1:]

print("Building Docker image...")

# build docker image
client = docker.from_env()

image, logs = client.images.build(path=tmp_dir, tag=repo_name)

print("Running Docker image...")

# run docker image, expose ports according to Dockerfile
ports = {}
for port in exposed_ports:
    ports[port] = None

container = client.containers.run(image, detach=True, ports=ports)

print("DONE")
