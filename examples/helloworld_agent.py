import asyncio

import fire

from metagpt.actions import Action
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.roles.role import RoleReactMode
from metagpt.schema import Message


class SimplePrint(Action):
    name: str = "SimplePrint"

    async def run(self, msg: Message) -> str:
        logger.info(f"{msg}")
        return msg + "!"


class SimplePrinter(Role):
    name: str = "XiaoGang"
    profile: str = "SimplePrinter"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_actions([SimplePrint, SimplePrint, SimplePrint])
        self._set_react_mode(react_mode=RoleReactMode.BY_ORDER.value)

    async def _act(self) -> Message:
        logger.info(f"{self._setting}: to do {self.rc.todo}({self.rc.todo.name})")
        todo = self.rc.todo
        msg = self.get_memories(k=1)[0]  # find the most recent messages
        new_msg = await todo.run(msg.content)
        msg = Message(content=new_msg, role=self.profile, cause_by=type(todo))
        self.rc.memory.add(msg)  # add the new message to memory
        return msg


def main():
    role = SimplePrinter()
    msg = 'Hello World!'
    result = asyncio.run(role.run(msg))
    logger.info(result)


if __name__ == "__main__":
    fire.Fire(main)