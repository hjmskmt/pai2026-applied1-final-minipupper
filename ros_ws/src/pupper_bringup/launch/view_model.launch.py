"""MiniPupper のモデル（URDF）を RViz に表示し、関節をスライダーで動かす。

    ros2 launch pupper_bringup view_model.launch.py
    ros2 launch pupper_bringup view_model.launch.py gui:=false   # スライダーなし（全関節 0）

起動するノード:
  robot_state_publisher      URDF と /joint_states から各リンクの位置を計算し /tf に流す
  joint_state_publisher(_gui) 関節の角度を /joint_states に流す（gui:=true でスライダー）
  rviz2                      /tf をもとにモデルを描く（Fixed Frame は base_link）

RViz かスライダーのウィンドウを閉じると、launch 全体が終了する。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, Shutdown
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    gui = LaunchConfiguration("gui")
    rviz = LaunchConfiguration("rviz")

    # robot_state_publisher は mini_pupper_description の launch を使う（xacro → URDF も中でやる）
    description = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([
                FindPackageShare("mini_pupper_description"),
                "launch",
                "mini_pupper_description.launch.py",
            ])
        )
    )

    return LaunchDescription([
        DeclareLaunchArgument("gui", default_value="true",
                              description="関節をスライダーで動かす（joint_state_publisher_gui）"),
        DeclareLaunchArgument("rviz", default_value="true", description="RViz を起動する"),
        description,
        Node(
            package="joint_state_publisher_gui",
            executable="joint_state_publisher_gui",
            condition=IfCondition(gui),
            on_exit=Shutdown(),
        ),
        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            condition=UnlessCondition(gui),
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            arguments=["-d", PathJoinSubstitution([
                FindPackageShare("pupper_bringup"), "rviz", "view_model.rviz",
            ])],
            condition=IfCondition(rviz),
            on_exit=Shutdown(),
        ),
    ])
