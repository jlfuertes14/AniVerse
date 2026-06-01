import subprocess

commands = [
    ["python", "test_all_apis.py", "https://shiroko.co/watch?id=16498&n=1", "iframe"],
    ["python", "test_all_apis.py", "https://animeverse.to/search?q=ATTACK+ON+TITAN", "boot-loader"],
    ["python", "test_all_apis.py", "https://anime.uniquestream.net/watch/PCdytjTt/To-You-2000-Years-in-the-Future-The-Fall-of-Zhiganshina-1", "iframe"]
]

for cmd in commands:
    print(f"\nRunning: {' '.join(cmd)}")
    subprocess.run(cmd)
