# ResolveRPC-macOS
It works only with **DaVinci Resolve Studio** and only on **macOS** because it uses **Resolve Scriping API** and **macOS specific paths**. 
Make sure you have scripting enabled inside `Preferences > General > General > External scripting using: Local`.

## Preview
![alt text](https://i.imgur.com/MADrkkt.png "Rich Presence")

## How to use it?
```bash
git clone https://github.com/jacobbvfx/ResolveRPC-macOS.git

cd ResolveRPC-macOS

pip3 install pypresence
pip3 install psutil

python3 resolve_rich_presence.py
```
## How to use it headlessly (in background)?
```bash
nohup python3 resolve_rich_presence.py &
```
## Will I ever make Windows or Linux version?
For some people this older project works on **Windows** [ResolveRPC](https://github.com/jacobbvfx/ResolveRPC) (it's very buggy).

## Will there ever be GUI or .app file?
Maybe.

## License
[GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/)