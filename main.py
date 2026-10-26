"""主入口"""

import uvicorn
from kzcts.config import settings


def main():
    """启动服务"""
    uvicorn.run(
        "kzcts.api.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )


if __name__ == "__main__":
    main()
