import os
import docker

from openai import OpenAI
from git import Repo

client = OpenAI()

repo_url = "https://github.com/BartlomiejRasztabiga/run-example.git"
repo_name = repo_url.split("/")[-1].replace(".git", "")

tmp_dir = f"./tmp/{repo_name}"

# clear dir
os.system(f"rm -rf {tmp_dir}")

# create dir
os.makedirs(tmp_dir, exist_ok=True)

# clone repo
repo = Repo.clone_from(repo_url, tmp_dir)

# get tree ignoring .git
tree = os.walk(tmp_dir)

# tree to string, ignoring .git
tree_str = ""
for root, dirs, files in tree:
    root_without_tmp = root.replace(tmp_dir, "")
    for file in files:
        if ".git" not in root:
            tree_str += f"{root_without_tmp}/{file}\n"

# print(tree_str)

prompt = f"""
Given this repository tree structure:

Tell me which files are the most important for generating Dockerfile to build a valid docker image that can be run to run the app of repository.

{tree_str}
"""

completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant, that given repository files structure will help to identify the most important files to generate a Dockerfile. Respond only with the file names, in the same format as provided.",
        },
        {"role": "user", "content": prompt},
    ],
    temperature=0.2
)

content = completion.choices[0].message.content

# get files from response and trim (strip)
files = list(map(lambda x: x.strip(), content.split("\n")))

# get files content
files_content = {}
for file in files:
    with open(tmp_dir + file, "r") as f:
        files_content[file] = f.read()


prompt = f"""
Given this repository files structure and content of the most important files, tell me how to generate a Dockerfile to build a valid docker image that can be run to run the app of repository.

{tree_str}

{files_content}
"""

completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant, that given repository files structure and content of the most important files will help to generate a Dockerfile to build a valid docker image that can be run to run the app of repository. Respond only with the content of the Dockerfile, ignore formatting markers.",
        },
        {"role": "user", "content": prompt},
    ],
    temperature=0.2
)

content = completion.choices[0].message.content

# write Dockerfile to tmp
with open(tmp_dir + "/Dockerfile", "w") as f:
    f.write(content)

exposed_ports = []
for line in content.split("\n"):
    if "EXPOSE" in line:
        exposed_ports = line.split(" ")[1:]

# DONE???

# build docker image
client = docker.from_env()

image, logs = client.images.build(path=tmp_dir, tag=repo_name)

print(image)

# run docker image, expose ports according to Dockerfile
ports = {}
for port in exposed_ports:
    ports[port] = port

container = client.containers.run(image, detach=True, ports=ports)

print(container)