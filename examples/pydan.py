from typing import Optional

from pydantic import BaseModel, field_validator


class FullName(BaseModel):
    last: str
    first: str

def starts_with_uppercase(s: str) -> bool:
    return s[0].isupper() if s else False

class User(BaseModel):
    id: int
    username: str
    email: str
    name: FullName

    @field_validator("name",  check_fields=False)
    @classmethod
    def check_sex(cls, v):
        if not (starts_with_uppercase(v.first) and starts_with_uppercase(v.last)):
            raise ValueError("First charactor should be uppercase ")
        return v


# 创建一个 User 对象并进行实例化
# user = User(id=1, username="john_doe", email="john@example.com")
# user = User(id=1, username="john_doe", email="john@example.com", name = {"last":"Gang"})
user = User(id=1, username="john_doe", email="john@example.com", name = {"last":"gang", "first":"Xiao"})

# 访问 User 对象的属性
print(user.id)  # 输出: 1
print(user.username)  # 输出: "john_doe"
print(user.email)  # 输出: "john@example.com"
