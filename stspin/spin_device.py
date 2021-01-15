from stspin.constants.command import PayloadSize
from typing import (
    Callable,
    List,
    Optional,
)
from typing_extensions import (
    Final,
)

from .constants import (
    Command,
    Constant,
    Register,
    Status,
)
from .utility import (
    toByteArrayWithLength,
    toInt, toSignedInt
)
from stspin import constants

class SpinDevice:
    """Class providing access to a single SPIN device"""

    def __init__(
            self, position: int,
            total_devices: int,
            spi_transfer: Callable[[List[int]], List[int]],
        ):
        """
        :position: Position in chain, where 0 is the last device in chain
        :total_devices: Total number of devices in chain
        :spi: SPI object used for serial communication
        """
        self._position: Final           = position
        self._total_devices: Final      = total_devices
        self._spi_transfer: Final       = spi_transfer

        self._direction                 = Constant.DirForward

    def _write(self, data: int) -> int:
        """Write a single byte to the device.

        :data: A single byte representing a command or value
        :return: Returns response byte
        """
        assert data >= 0
        assert data <= 0xFF

        buffer = [Command.Nop] * self._total_devices
        buffer[self._position] = data

        response = self._spi_transfer(buffer)

        return response[self._position]

    def _writeMultiple(self, data: List[int]) -> int:
        """Write each byte in list to device
        Used to combine calls to _write

        :data: List of single byte values to send
        :return: Response bytes as int
        """
        response = []

        for data_byte in data:
            response.append(self._write(data_byte))

        return toInt(response)

    def _writeCommand(
            self, command: int,
            payload: Optional[int] = None,
            payload_size: Optional[int] = None) -> int:
        """Write command to device with payload (if any)

        :command: Command to write
        :payload: Payload (if any)
        :payload_size: Payload size in bytes
        :return: Response bytes as int
        """
        
        assert (payload is None) == (payload_size is None), \
            'payload and payload_size must be either both None, xor present'

        response = self._write(command)

        # payload_size does not need to be checked here,
        # but mypy is not quite that advanced yet
        if payload is None or payload_size is None:
            return response

        return self._writeMultiple(
            toByteArrayWithLength(payload, payload_size)
        )

    def setRegister(self, register: int, value: int) -> None:
        """Set the specified register to the given value
        
        :register: The register location
        :value: Value register should be set to
        """
        RegisterSize = Register.getSize(register)
        set_command = Command.ParamSet | register

        self._writeCommand(set_command, value, RegisterSize)

    def getRegister(self, register: int) -> int:
        """Fetches a register's contents and returns the current value

        :register: Register location to be accessed
        :returns: Value of specified register
        """
        
        RegisterSize = Register.getSize(register)
        self._writeCommand(Command.ParamGet | register)

        return self._writeMultiple([Command.Nop] * RegisterSize)

    def move(self, steps: int) -> None:
        """Move motor n steps

        :steps: Number of (micro)steps to take
        """
        
        assert steps >= -Constant.MaxSteps
        assert steps <= Constant.MaxSteps
        
        steps = self._toAbsAndDir(steps) 
        PayloadSize = Command.getPayloadSize(Command.Move)

        self._writeCommand(Command.Move | self._direction, steps, PayloadSize)

    def run(self, steps_per_second: float) -> None:
        """Run the motor at the given steps per second

        :steps_per_second: Full steps per second from -15625 up to 15625.
        0.015 step/s resolution
        """
        
        assert steps_per_second >= -Constant.MaxStepsPerSecond
        assert steps_per_second <= Constant.MaxStepsPerSecond
        
        speed = int(steps_per_second * Constant.SpsToSpeed)
        speed = self._toAbsAndDir(speed)
        PayloadSize = Command.getPayloadSize(Command.Run)

        self._writeCommand(Command.Run | self._direction, speed, PayloadSize)
        
    def gotoDir(self, direction: int, position: int) -> None:
        """Go to absolute position in a specified direction
        
        :direction: Constant.DirReverse or Constant.DirForward (0 or 1)
        :position: Absolute position in (micro)steps.
        """
        assert direction >= 0
        assert direction < Constant.DirMax
        assert position < 1<<22
        assert position > -(1<<22)
        
        self._direction=direction

        PayloadSize = Command.getPayloadSize(Command.GoToDir)
        self._writeCommand(Command.GoToDir | self._direction, position, PayloadSize)
        
    def goto(self,position: int, steps_per_second: float) -> None:
        """Go to absolute position using the shortest way and at the given speed
        
        :position: absolute position in (micro)steps
        :steps_per_second: Full steps per second from 0 up to 15625.
        0.015 step/s resolution
        """
        assert position < 1<<22
        assert position > -(1<<22)
        assert steps_per_second > 0
        assert steps_per_second <= Constant.MaxStepsPerSecond
        
        speed = int(steps_per_second * Constant.SpsToSpeed)
        oldMaxSpd = self.getRegister(Register.SpeedMin)
        self.setRegister(Register.SpeedMax,speed)
        PayloadSize = Command.getPayloadSize(Command.GoTo)
        
        self._writeCommand(Command.GoTo |  position, PayloadSize)
        self.setRegister(Register.SpeedMax,oldMaxSpd)

    def goUntil(self, action: int, steps_per_second: float) -> None:
        """Go at the givien speed until the switch triggers.
        
        :action:    Constant.ActResetPos reset the absolute position to 0
                    Constant.ActSetMark sets the MARK register to the current position    
        :steps_per_second: Full steps per second from -15625 up to 15625.
        0.015 step/s resolution
        """
        
        assert steps_per_second > -Constant.MaxStepsPerSecond
        assert steps_per_second < Constant.MaxStepsPerSecond
        assert action >= 0
        assert action < 2
        assert steps_per_second > -Constant.MaxStepsPerSecond
        assert steps_per_second < Constant.MaxStepsPerSecond
        
        speed = int(steps_per_second * Constant.SpsToSpeed)
        speed = self._toAbsAndDir(speed)
        PayloadSize = Command.getPayloadSize(Command.GoUntil)
        
        self._writeCommand(Command.GoUntil | action, self.direction, speed, PayloadSize)

    def releaseSw(self, action: int, steps_per_second: float) ->None:
        """Move the motor at the given speed until the switch is released
        
        :steps_per_second: Full steps per second from -15625 up to 15625.
        0.015 step/s resolution
        """
        assert action >= 0
        assert action < 2
        assert steps_per_second != 0
        
        speed = int(steps_per_second * Constant.SpsToSpeed)
        speed = self._toAbsAndDir(speed)
        oldMinSpd = self.getRegister(Register.SpeedMin)
        self.setRegister(Register.SpeedMin,speed)
        PayloadSize = Command.getPayloadSize(Command.ReleaseSw)
        
        self._writeCommand(Command.ReleaseSw | action, self.direction, PayloadSize)
        self.setRegister(Register.SpeedMin,oldMinSpd)
                
    def setEndStopAndCenter(self, steps_per_second:float) ->None:
        """For a motor acting on a linear rail with 2 endstops, set the
        ABS_POS position at the minimum displacement value and the MARK position
        at the other end and go to the center.
        Only if the motor runs less than 2^21 steps end to end. (2097152 steps)
        Endstops must be connected NC and wired in serie.
        
        :steps_per_second: Full steps per second from 0 up to 15625.
        0.015 step/s resolution
        """
        
        assert steps_per_second > 0
        assert steps_per_second < Constant.MaxStepsPerSecond
        
        self.goUntil(Constant.ActResetPos,-steps_per_second)
        while self.isBusy():
            pass
        self.releaseSw(Constant.ActResetPos,steps_per_second/20)
        while self.isBusy():
            pass
        self.goUntil(Constant.ActSetMark, steps_per_second)
        while self.isBusy():
            pass
        self.releaseSw(Constant.ActSetMark,-steps_per_second/20)
        while self.isBusy():
            pass
        self.gotoDir(Constant.DirReverse,self.getMark()/2)
        while self.getSpeed() < 0:
            pass
        print("position reset completed")
              
    def hiZHard(self) -> None:
        """Stop motors abruptly, release holding current

        """
        self._writeCommand(Command.HiZHard)

    def hiZSoft(self) -> None:
        """Stop motors, release holding current

        """
        self._writeCommand(Command.HiZSoft)

    def stopHard(self) -> None:
        """Stop motors abruptly, maintain holding current

        """
        self._writeCommand(Command.StopHard)

    def stopSoft(self) -> None:
        """Stop motors, maintain holding current

        """
        self._writeCommand(Command.StopSoft)
        
    def getPosition(self) -> int:
        """Returns signed absolute position from register value
        
        :return: absolute position in (micro)steps
        """   
        rawdata = self.getRegister(Register.PosAbs)
        
        return toSignedInt(rawdata)
            
    def setPosition(self, position: int) -> None:
        """Set position register to arbitrary value
        
        :position: absolute position in (micro)steps
        """
        assert position < 1<<22
        assert position > -1<<22
        
        self.setRegister(Register.PosAbs,position)
        
    def getMark(self) -> int:
        """Return Mark position
        
        :return: absolute position in (micro)steps
        """
        rawdata = self.getRegister(Register.Mark)
        return toSignedInt(rawdata)

    def setMark(self, position:int) -> None:
        """set MARK register to arbitrary value
        
        :position: absolute position in (micro)steps
        """
        assert position < 1<<22
        assert position > -1<<22
        
        self.setRegister(Register.Mark,position)
        
    def getSpeed(self) ->float:
        """Get actual speed
        :return: signed speed in fullsteps / seconds
        """
        stepsPerTick=self.getRegister(Register.Speed)
        dir=self.getDir()
        if ~dir:
            stepsPerTick*=-1
        return stepsPerTick/Constant.SpsToSpeed

    def getStatus(self) -> int:
        """Get status register
        Resets alarm flags. Does not reset HiZ
        
        :returns: 2 bytes status as an int
        """
        self._writeCommand(Command.StatusGet)

        return self._writeMultiple([Command.Nop] * 2)

    def isBusy(self) -> bool:
        """Checks busy status of the device
        
        :returns: True if device is busy, else False
        """
        # We use getRegister instead of getStatus
        # So as not to clear any warning flags
        status = self.getRegister(Register.Status)

        return False if (status & Status.NotBusy) else True
    
    def getDir(self) -> bool:
        """Get the direction flag
        
        :returns: True if direction is forward False if reverse (1 or 0)
        """
        status = self.getRegister(Register.Status)
        
        return True if (status & Status.Dir) else False

    def _toAbsAndDir(self,signedvalue: int) -> int:
        """Converts a signed integer value (position or speed) to absolute value + corresponding direction
        
        signedvalue: signed integer (speed or position)
        """
        
        if signedvalue<0:
            self._direction = Constant.DirReverse
            signedvalue *= -1
        else:
            self._direction = Constant.DirForward    
        return signedvalue
