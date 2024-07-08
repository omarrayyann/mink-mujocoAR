from dm_control import mjcf
import mujoco
import mujoco.viewer
import numpy as np
import mink
from pathlib import Path
from loop_rate_limiters import RateLimiter
from mink.utils import set_mocap_pose_from_site


_HERE = Path(__file__).parent
_XML = _HERE / "universal_robots_ur5e" / "ur5e.xml"


def construct_model():
    root = mjcf.RootElement()
    root.statistic.meansize = 0.08
    getattr(root.visual, "global").azimuth = -120
    getattr(root.visual, "global").elevation = -20

    root.worldbody.add("light", pos="0 0 1.5", directional="true")

    base = root.worldbody.add("body", name="base")
    width, height, depth = 0.8, 0.4, 0.2
    base.add(
        "geom",
        type="box",
        size=[width, height, depth],
        density=1e-3,
        rgba=".9 .8 .6 1",
    )
    base.pos = [-0.0 * width, -0.0 * height, -0.5 * depth]
    base.add("freejoint")
    base.add("site", name="base", pos=[0, 0, depth], group=1)
    left_site = base.add("site", name="l_attachment_site", pos=[0.3, 0, depth], group=5)
    right_site = base.add(
        "site",
        name="r_attachment_site",
        pos=[-0.3, 0, depth],
        group=5,
    )

    left_ur5e = mjcf.from_path(_XML.as_posix())
    left_ur5e.model = "l_ur5e"
    left_ur5e.find("key", "home").remove()
    left_site.attach(left_ur5e)

    right_ur5e = mjcf.from_path(_XML.as_posix())
    right_ur5e.model = "r_ur5e"
    right_ur5e.find("key", "home").remove()
    right_site.attach(right_ur5e)

    body = root.worldbody.add("body", name="base_target", mocap=True)
    body.add(
        "geom",
        type="box",
        size=".05 .05 .05",
        contype="0",
        conaffinity="0",
        rgba=".6 .3 .3 .5",
    )

    body = root.worldbody.add("body", name="l_target", mocap=True)
    body.add(
        "geom",
        type="box",
        size=".05 .05 .05",
        contype="0",
        conaffinity="0",
        rgba=".3 .6 .3 .5",
    )

    body = root.worldbody.add("body", name="r_target", mocap=True)
    body.add(
        "geom",
        type="box",
        size=".05 .05 .05",
        contype="0",
        conaffinity="0",
        rgba=".3 .3 .6 .5",
    )

    return mujoco.MjModel.from_xml_string(root.to_xml_string(), root.get_assets())


if __name__ == "__main__":
    model = construct_model()

    configuration = mink.Configuration(model)

    tasks = [
        base_task := mink.FrameTask(
            frame_name="base",
            frame_type="site",
            position_cost=1.0,
            orientation_cost=1.0,
        ),
        left_ee_task := mink.FrameTask(
            frame_name="l_ur5e/attachment_site",
            frame_type="site",
            position_cost=1.0,
            orientation_cost=1.0,
        ),
        right_ee_task := mink.FrameTask(
            frame_name="r_ur5e/attachment_site",
            frame_type="site",
            position_cost=1.0,
            orientation_cost=1.0,
        ),
    ]

    limits = [
        mink.ConfigurationLimit(model=model),
    ]

    base_mid = model.body("base_target").mocapid[0]
    left_mid = model.body("l_target").mocapid[0]
    right_mid = model.body("r_target").mocapid[0]
    model = configuration.model
    data = configuration.data
    solver = "quadprog"

    with mujoco.viewer.launch_passive(
        model=model, data=data, show_left_ui=False, show_right_ui=False
    ) as viewer:
        mujoco.mjv_defaultFreeCamera(model, viewer.cam)
        viewer.opt.frame = mujoco.mjtFrame.mjFRAME_SITE

        set_mocap_pose_from_site(model, data, "base_target", "base")
        set_mocap_pose_from_site(model, data, "l_target", "l_ur5e/attachment_site")
        set_mocap_pose_from_site(model, data, "r_target", "r_ur5e/attachment_site")

        rate = RateLimiter(frequency=200.0)
        t = 0.0
        while viewer.is_running():
            data.mocap_pos[base_mid][2] = 0.3 * np.sin(2.0 * t)
            base_task.set_target_from_mocap(data, base_mid)

            data.mocap_pos[left_mid][1] = 0.5 + 0.2 * np.sin(2.0 * t)
            data.mocap_pos[left_mid][2] = 0.2
            left_ee_task.set_target_from_mocap(data, left_mid)

            data.mocap_pos[right_mid][1] = 0.5 + 0.2 * np.sin(2.0 * t)
            data.mocap_pos[right_mid][2] = 0.2
            right_ee_task.set_target_from_mocap(data, right_mid)

            vel = mink.solve_ik(configuration, tasks, limits, rate.dt, solver, 1e-2)
            configuration.integrate_inplace(vel, rate.dt)

            viewer.sync()
            rate.sleep()
            t += rate.dt
