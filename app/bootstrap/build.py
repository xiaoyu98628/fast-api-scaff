from app.bootstrap.container import ApplicationContainer


def build_application_container() -> ApplicationContainer:
    """构建并连接应用所需的组件。"""
    return ApplicationContainer()
