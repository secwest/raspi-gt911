#!/usr/bin/env python3

import struct
import sys
import os
import subprocess
import time
import getpass
from typing import Dict, Any, Tuple, Optional

# Configuration presets for common displays
PRESETS = {
    '7inch': {
        'x_max': 1024,
        'y_max': 600,
        'touch_threshold': 16,
        'num_touch_points': 5,
        'filter_coefficient': 4
    },
    '5inch': {
        'x_max': 800,
        'y_max': 480,
        'touch_threshold': 20,
        'num_touch_points': 5,
        'filter_coefficient': 4
    },
    'waveshare7': {
        'x_max': 1280,
        'y_max': 800,
        'touch_threshold': 28,
        'num_touch_points': 5,
        'filter_coefficient': 4
    }
}


class SudoHandler:
    """Handle sudo operations and privilege management."""
    def __init__(self):
        self._sudo_password: Optional[str] = None
        self._sudo_timestamp = 0
        self._sudo_timeout = 300  # 5 minutes

    def _check_sudo_access(self) -> bool:
        try:
            result = subprocess.run(
                ['sudo', '-n', 'true'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_sudo_password(self) -> Optional[str]:
        try:
            if self._sudo_password is None:
                self._sudo_password = getpass.getpass("Enter sudo password: ")
            return self._sudo_password
        except (KeyboardInterrupt, EOFError):
            print("\nPassword prompt cancelled.")
            return None

    def run_sudo_command(self, command: list, silent: bool = False) -> Tuple[bool, str]:
        current_time = time.time()
        
        if not self._check_sudo_access():
            password = self._get_sudo_password()
            if password is None:
                return False, "Sudo password required but not provided"

            try:
                proc = subprocess.Popen(
                    ['sudo', '-S'] + command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                output, error = proc.communicate(input=password + '\n')
                
                if proc.returncode == 0:
                    self._sudo_timestamp = current_time
                    if not silent and output:
                        print(output.strip())
                    return True, ""
                else:
                    self._sudo_password = None
                    return False, error.strip()
                    
            except Exception as e:
                return False, str(e)
        else:
            try:
                result = subprocess.run(
                    ['sudo'] + command,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    if not silent and result.stdout:
                        print(result.stdout.strip())
                    return True, ""
                else:
                    return False, result.stderr.strip()
            except Exception as e:
                return False, str(e)


# Global sudo handler instance
sudo_handler = SudoHandler()


def validate_resolution(x_max: int, y_max: int) -> None:
    if not (0 < x_max <= 4095 and 0 < y_max <= 4095):
        raise ValueError("Resolution must be between 1 and 4095")
    # GT911 typically wants even X/Y. Adjust if needed
    if x_max % 2 != 0 or y_max % 2 != 0:
        raise ValueError("Resolution values must be even numbers")


def check_system_requirements() -> Tuple[bool, str]:
    """
    Checks if /lib/firmware directory exists, modprobe is installed,
    and the Goodix driver module is available. 
    If your system doesn't have the Goodix driver built, it will fail here.
    """
    try:
        if not os.path.isdir('/lib/firmware'):
            return False, "Directory /lib/firmware does not exist"
        
        result = subprocess.run(['which', 'modprobe'], capture_output=True, text=True)
        if result.returncode != 0:
            return False, "modprobe command not found"
        
        # Check if 'goodix' driver is recognized by modprobe
        result = subprocess.run(['modprobe', '-n', 'goodix'], capture_output=True, text=True)
        if result.returncode != 0:
            return False, "Goodix driver module not available"
        
        return True, "System requirements met"
    except Exception as e:
        return False, f"Error checking system requirements: {str(e)}"


def generate_goodix_config(x_max: int = 1024,
                           y_max: int = 600,
                           touch_threshold: int = 16,
                           num_touch_points: int = 5,
                           filter_coefficient: int = 4) -> bytearray:
    """
    Build a 186-byte configuration for a Goodix GT911 device, aligned to:
      0x8047 -> index 0 ... 0x80FF -> index 184, 0x8100 -> index 185
    with an 8-bit checksum at index 184 and 0x01 at index 185.
    """
    validate_resolution(x_max, y_max)

    # 186 bytes total: 0..183 => the main config area, 184 => checksum, 185 => config_fresh
    config = bytearray(186)
    for i in range(186):
        config[i] = 0x00

    # According to GT911 doc:
    #  Byte 0   => 0x8047 (Config_Version)
    #  Byte [1..2] => 0x8048..49 (X resolution)
    #  Byte [3..4] => 0x804A..4B (Y resolution)
    #  Byte 5   => 0x804C (Number of touches)
    #  Byte 6   => 0x804D (Module_Switch1)
    #  Byte 7   => 0x804E (Module_Switch2)
    #  Byte 8   => 0x804F (Shake_Count)
    #  Byte 9   => 0x8050 (Filter)
    #  Byte 12  => 0x8053 (Screen_Touch_Level) if needed
    #  ...
    #  Byte 184 => 0x80FF (8-bit checksum)
    #  Byte 185 => 0x8100 (Config_Fresh)

    # 0x8047: Config_Version
    config[0] = 0x01  # example version

    # 0x8048..49: X resolution
    struct.pack_into('<H', config, 1, x_max)

    # 0x804A..4B: Y resolution
    struct.pack_into('<H', config, 3, y_max)

    # 0x804C: Number of Touches
    config[5] = min(max(1, num_touch_points), 10)

    # 0x804D: Module_Switch1
    #  bits: 7 = Y2Y, 6 = X2X, etc.  0x00 => no swap, no invert
    config[6] = 0x00

    # 0x804E: Module_Switch2
    config[7] = 0x00

    # 0x804F: Shake_Count
    config[8] = 0x03

    # 0x8050: Filter
    config[9] = filter_coefficient & 0xFF

    # 0x8053: Screen_Touch_Level (threshold)
    # offset to 0x8053 = 0x8053 - 0x8047 = 0x0C decimal = 12
    config[12] = max(1, touch_threshold)

    # (You can add more parameter writes here if needed,
    #  e.g. noise threshold, etc.)

    # ----- 8-bit Checksum across bytes [0..183] -----
    sum_8 = sum(config[0:184]) & 0xFF
    checksum_8 = ((~sum_8) + 1) & 0xFF
    config[184] = checksum_8  # 0x80FF

    # ----- CONFIG_FRESH = 0x01 -----
    config[185] = 0x01        # 0x8100

    return config


def print_config_details(config: bytearray) -> None:
    """
    Print key details from the GT911 config array 
    (using official offset alignment).
    """
    # Byte 0 => 0x8047
    config_version = config[0]

    # Byte 1..2 => X resolution
    x_res = struct.unpack_from('<H', config, 1)[0]

    # Byte 3..4 => Y resolution
    y_res = struct.unpack_from('<H', config, 3)[0]

    # Byte 5 => Number of touches
    touches = config[5]

    # Byte 6 => Module_Switch1
    mswitch1 = config[6]

    # Byte 7 => Module_Switch2
    mswitch2 = config[7]

    # Byte 8 => Shake_Count
    shake = config[8]

    # Byte 9 => Filter
    flt = config[9]

    # Byte 12 => 0x8053 => Screen_Touch_Level
    threshold = config[12]

    # Byte 184 => 0x80FF => 8-bit checksum
    csum = config[184]

    # Byte 185 => 0x8100 => Config_Fresh
    fresh = config[185]

    print("\n=== GT911 Configuration Details (Correct Format) ===")
    print(f" Config_Version (0x8047):       0x{config_version:02X}")
    print(f" X Resolution (0x8048..49):     {x_res}")
    print(f" Y Resolution (0x804A..4B):     {y_res}")
    print(f" Touch Points (0x804C):         {touches}")
    print(f" Module_Switch1 (0x804D):       0x{mswitch1:02X}")
    print(f" Module_Switch2 (0x804E):       0x{mswitch2:02X}")
    print(f" Shake_Count (0x804F):          {shake}")
    print(f" Filter (0x8050):               {flt}")
    print(f" Screen_Touch_Level (0x8053):   {threshold}")
    print(f" Checksum (0x80FF):             0x{csum:02X}")
    print(f" Config_Fresh (0x8100):         0x{fresh:02X}")
    print("======================================================")


def save_config_file(config: bytearray, filename: str = "goodix_911_cfg.bin") -> bool:
    """Save the configuration bytearray to a file."""
    try:
        with open(filename, "wb") as f:
            f.write(config)
        print(f"\nConfiguration saved to '{filename}' successfully.")
        return True
    except IOError as e:
        print(f"\nError saving configuration: {e}")
        return False
    except Exception as e:
        print(f"\nUnexpected error saving configuration: {e}")
        return False


def install_config(config: bytearray, temp_file: str = "goodix_911_cfg.bin") -> bool:
    """Install the configuration file to /lib/firmware with proper permissions."""
    try:
        # Check system requirements first
        requirements_met, message = check_system_requirements()
        if not requirements_met:
            print(f"\nSystem requirements not met: {message}")
            return False

        # First save to temporary file
        with open(temp_file, "wb") as f:
            f.write(config)

        # Copy file to firmware directory
        success, error = sudo_handler.run_sudo_command(
            ['cp', temp_file, '/lib/firmware/goodix_911_cfg.bin']
        )
        if not success:
            print(f"Error copying file: {error}")
            return False

        # Set permissions
        success, error = sudo_handler.run_sudo_command(
            ['chmod', '644', '/lib/firmware/goodix_911_cfg.bin']
        )
        if not success:
            print(f"Error setting permissions: {error}")
            return False

        try:
            os.remove(temp_file)
        except OSError:
            print("Warning: Could not remove temporary file")

        # Offer to reload the driver
        print("\nConfiguration installed successfully.")
        while True:
            reload = input("Would you like to reload the goodix driver? (y/N): ").lower()
            if reload in ['y', 'n', '']:
                break
            print("Please enter 'y' or 'n'")

        if reload == 'y':
            print("\nReloading driver...")
            success, error = sudo_handler.run_sudo_command(['modprobe', '-r', 'goodix'])
            if not success:
                print(f"Error unloading driver: {error}")
                return False

            time.sleep(1)  # Give system time to unload

            success, error = sudo_handler.run_sudo_command(['modprobe', 'goodix'])
            if not success:
                print(f"Error loading driver: {error}")
                return False

            print("Driver reloaded. Please check dmesg for results:")
            print("Command: dmesg | grep Goodix")
        else:
            print("\nDriver not reloaded. Changes will take effect after reboot.")

        return True

    except Exception as e:
        print(f"Installation error: {e}")
        return False


def get_validated_input(prompt: str, min_val: int, max_val: int, current_val: int) -> int:
    """Get and validate numeric input within specified range."""
    while True:
        try:
            value = input(f"{prompt} ({min_val}-{max_val}) [{current_val}]: ")
            if not value:  # Empty input => use current value
                return current_val
            value = int(value)
            if min_val <= value <= max_val:
                return value
            print(f"Value must be between {min_val} and {max_val}")
        except ValueError:
            print("Please enter a valid number")


def load_preset(name: str) -> Dict[str, Any]:
    """Load preset configuration values."""
    if name not in PRESETS:
        print(f"Unknown preset '{name}'. Using default values.")
        return PRESETS['7inch']
    return PRESETS[name].copy()


def print_presets() -> None:
    """Print available presets and their details."""
    print("\nAvailable Presets:")
    for pname, cfg in PRESETS.items():
        print(f"\n{pname}:")
        print(f"  Resolution:        {cfg['x_max']}x{cfg['y_max']}")
        print(f"  Touch Threshold:   {cfg['touch_threshold']}")
        print(f"  Number of Touches: {cfg['num_touch_points']}")
        print(f"  Filter Coefficient:{cfg['filter_coefficient']}")


def interactive_menu() -> None:
    """Interactive menu for generating and installing GT911 configurations."""
    settings = PRESETS['7inch'].copy()

    while True:
        print("\n=== GT911 Configuration Generator ===")
        print("\nCURRENT SETTINGS:")
        print(f"  1) Resolution:        {settings['x_max']}x{settings['y_max']}")
        print(f"  2) Touch Threshold:   {settings['touch_threshold']}")
        print(f"  3) Number of Touches: {settings['num_touch_points']}")
        print(f"  4) Filter Coefficient:{settings['filter_coefficient']}")

        print("\nACTIONS:")
        print("  5) Show Available Presets")
        print("  6) Load Preset")
        print("  7) Generate and Save Configuration")
        print("  8) Generate and Install Configuration")
        print("  9) Show Detailed Configuration")
        print("  0) Exit")
        print("\nEnter a number to modify setting or perform action")

        choice = input("\nChoice: ").strip()

        try:
            if choice == '1':
                settings['x_max'] = get_validated_input(
                    "X Resolution", 2, 4094, settings['x_max']
                )
                settings['y_max'] = get_validated_input(
                    "Y Resolution", 2, 4094, settings['y_max']
                )
            elif choice == '2':
                settings['touch_threshold'] = get_validated_input(
                    "Touch Threshold", 1, 255, settings['touch_threshold']
                )
            elif choice == '3':
                settings['num_touch_points'] = get_validated_input(
                    "Number of Touch Points", 1, 10, settings['num_touch_points']
                )
            elif choice == '4':
                settings['filter_coefficient'] = get_validated_input(
                    "Filter Coefficient", 0, 15, settings['filter_coefficient']
                )
            elif choice == '5':
                print_presets()
            elif choice == '6':
                print_presets()
                preset = input("\nEnter preset name: ").strip().lower()
                settings = load_preset(preset)
            elif choice == '7':
                config = generate_goodix_config(**settings)
                filename = input("Enter filename [goodix_911_cfg.bin]: ").strip()
                if not filename:
                    filename = "goodix_911_cfg.bin"
                save_config_file(config, filename)
            elif choice == '8':
                config = generate_goodix_config(**settings)
                print("\nGenerating and installing configuration...")
                if install_config(config):
                    print("Installation completed.")
                else:
                    print("Installation failed.")
            elif choice == '9':
                config = generate_goodix_config(**settings)
                print_config_details(config)
            elif choice == '0':
                print("\nExiting configuration generator.")
                break
            else:
                print("\nInvalid choice. Please try again.")
        except ValueError as e:
            print(f"\nError: {e}")
        except Exception as e:
            print(f"\nUnexpected error: {e}")


def main():
    """Main entry point with enhanced error handling."""
    if os.geteuid() != 0:
        print("\nNote: Some functions will require sudo privileges.")
        print("You will be prompted for your password when needed.")
    
    try:
        print("GT911 Configuration Generator")
        print("This utility generates and installs configuration files for GT911 controllers.")
        
        # Check system requirements at startup
        requirements_met, message = check_system_requirements()
        if not requirements_met:
            print(f"\nWarning: {message}")
            print("Some features may not work correctly.")
        
        interactive_menu()
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
