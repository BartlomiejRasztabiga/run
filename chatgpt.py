import os
import docker

from dotenv import load_dotenv
from openai import OpenAI
from git import Repo

load_dotenv()

client = OpenAI()

model = "gpt-4o-mini"
temperature = 0.2

repo_url = "https://github.com/BartlomiejRasztabiga/run-example.git"
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
tree = os.walk(tmp_dir)

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
            "content": "You are a helpful assistant, that given repository files structure will help to identify the most important files to generate a Dockerfile to build a valid docker image that can be run to run the app of repository. Respond only with the file names, in the same format as provided.",
        },
        {"role": "user", "content": tree_str},
    ],
    temperature=temperature,
)

content = completion.choices[0].message.content

print("Preparing files content...")

# get files from response and trim (strip)
files = list(map(lambda x: x.strip(), content.split("\n")))

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
            "content": "You are a helpful assistant, that given repository files structure and content of the most important files will help to generate a Dockerfile to build a valid docker image that can be run to run the app of repository. Use latest base image versions and best practises, implement all security measures and expose all necessary ports. Respond only with the content of the Dockerfile, ignore formatting markers.",
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
