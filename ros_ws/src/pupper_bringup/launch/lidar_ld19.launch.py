"""LiDAR（LDROBOT STL-19P = LD19）を、ロボットへの取り付けの向きに合わせて起動する。

third_party の ld19.launch.py との違い：
- base_link → base_laser の TF の yaw を、実物の向き（公式の取り付けと 180° 逆）に合わせる
  （2026-10-29 に、正面の物が +x・左の物が +y に出ることを確認。.claude/plans/worklog/2026-10-28_lidar.md）

ロボットには pupper_bringup が無いので、ファイルを送ってパスで起動する：
  ros2 launch ~/lidar_ld19.launch.py
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # LiDAR ドライバ（パラメータは ld19.launch.py と同じ）
    ldlidar_node = Node(
        package='ldlidar_stl_ros2',
        executable='ldlidar_stl_ros2_node',
        name='LD19',
        output='screen',
        parameters=[
            {'product_name': 'LDLiDAR_LD19'},
            {'topic_name': 'scan'},
            {'frame_id': 'base_laser'},
            {'port_name': '/dev/ttyUSB0'},
            {'port_baudrate': 230400},
            {'laser_scan_dir': True},
            {'enable_angle_crop_func': False},
            {'angle_crop_min': 135.0},
            {'angle_crop_max': 225.0},
        ],
    )

    base_link_to_laser_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_base_laser_ld19',
        arguments=['0','0','0.18','-1.57','0','0','base_link','base_laser']#x y z yaw pitch roll 親 子
    )


    return LaunchDescription([
        ldlidar_node,
        base_link_to_laser_tf_node,
    ])
