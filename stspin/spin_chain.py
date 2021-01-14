from stspin.constants.register import RegisterSize
from stspin.constants.constant import Constant
from stspin.constants.command import Command
from stspin.utility import toByteArray, toByteArrayWithLength, toInt, toPlusAndDir, toSignedInt, transpose
from typing import (
    Callable,
    List,
    Optional,
    Tuple,
)
from typing_extensions import (
    Final,
)
from itertools import zip_longest

from . import SpinDevice, Register

class SpinChain:
    """Class for constructing a chain of SPIN devices"""
    
    def __init__(
            self, total_devices: int,
            spi_select: Optional[Tuple[int, int]] = None,
            spi_transfer: Optional[
                Callable[[List[int]], List[int]]
            ] = None,
        ) -> None:
        """
        if different from hardware SPI CS pin
        :total_devices: Total number of devices in chain
        :spi_select: A SPI bus, device pair, e.g. (0, 0)
        :spi_transfer: A SPI transfer function that behaves like
            spidev.xfer2.
            It should write a list of bytes as ints with MSB first,
            while correctly latching using the chip select pins
            Then return an equal-length list of bytes as ints from MISO

        """
        assert total_devices > 0
        assert (spi_select is None) != (spi_transfer is None), \
            'Either supply a SPI transfer function or use spidev\'s'

        self._total_devices: Final = total_devices

        # {{{ SPI setup
        if spi_transfer is not None:
            self._spi_transfer = spi_transfer

        elif spi_select is not None:
            import spidev
            self._spi: Final = spidev.SpiDev()

            bus, device = spi_select
            self._spi.open(bus, device)

            self._spi.mode = 3
            # Device expects MSB to be sent first
            self._spi.lsbfirst = False
            self._spi.max_speed_hz = 5000000
            # CS pin is active low
            self._spi.cshigh = False

            self._spi_transfer = self._spi.xfer2
        # }}}
        
        self._resetCommands()

    def create(self, position: int) -> SpinDevice:
        """
                   +----------+
              MOSI |   MCU    | MISO
       +-----------+          +---------------+
       |           +----------+               |
       |                                      |
       |                                      |
       |             SPIN ICs                 |
       |   +-----+     +-----+     +-----+    |
       |SDI|     |     |     |     |     |SDO |
       +---+  2  +-----+  1  +-----+  0  +----+
           |     |     |     |     |     |
           |     |     |     |     |     |
           +-----+     +-----+     +-----+
        Create a new SPIN device at the specified chain location
        :position: Device position in chain
        :return: A newly-instantiated SpinDevice

        """
        assert position >= 0
        assert position < self._total_devices

        return SpinDevice(
            position,
            self._total_devices,
            self._spi_transfer,
        )
        
    def _resetCommands(self):
        """
        """
        try: self.commands
        except NameError:
            pass
        else: del self.commands
        
        self.commands = [Command.Nop] * self._total_devices
        self.datasize = [0] * self._total_devices
                       
    def addCommand(self, data) -> None:
        """
        """
        position = data[0]
        command = data[1]

        self.commands[position] = command
        self.datasize[position] = len(data)-2
        
        if len(data) > 2:
                    
            self.commands[position].append(data[i] for i in range(2,len(data)))
                              
    def _pllwrite(self,data:List[int]):
        """Write a single byte to all devices in the chain
        :data: list of bytes to send
        :return: response list 
        """
        
        if len(data) != self._total_devices:
            pass

        return self._spi_transfer(data)
    
    def _getResponses(self,data,datalenght):
        """
        """
        response = []*self._total_devices
        
        for i in self._total_devices:
            
            if datalenght[i] == 0:
                response[i] = None
            
            else:
                response[i] = toInt(data[0:datalenght[i]])
                
        return response
                            
    def runCommands(self, data:List[List[int]]):
        """Write some bytes to all devices
        :data: List containing list of byte indexed by postiton in the chain
            MSB coming first.
        :return: List of responses, MSB first
        """        
        responses = []
        data_byte =[]
        
        datat = list(zip_longest(cmd for cmd in data, fillvalue = Command.Nop))
        
        if len(datat[0]) != self._total_devices:
            pass

        for i in self._total_devices:

            for data_byte in datat[i]:
                responses[i].append(self._pllwrite(data_byte))
        
        size = self.datasize
        self._resetCommands()
        
        return self._getResponses(list(zip(row for row in responses)),size)
    
    def allSoftStop(self):
        """
        """
        command = [Command.StopSoft] * self._total_devices
        
        self.runCommands(command)
        
    def allHardStop(self):
        """
        """
        command = [Command.StopHard] * self._total_devices
        
        self.runCommands(command)

    def allHiZSoft(self):
        """
        """
        command = [Command.HiZSoft] * self._total_devices
        
        self.runCommands(command)
        
    def allHiZHard(self):
        """
        """
        command = [Command.HiZHard] * self._total_devices
        
        self.runCommands(command)
        
    def allgetRegister(self, register: int) -> int:
        """Fetches a register's contents and returns the current value

        :register: Register location to be accessed
        :returns: Value of specified register
        """
        
        RegisterSize = Register.getSize(register)
        self.datasize = [RegisterSize] * self._total_devices
        
        command = [Command.ParamGet | register, Command.Nop * RegisterSize] * self._total_devices 
        
        return self.runCommands[command]
        
    def allGetPosition(self):
        """
        """
        data = []
        rawdata = self.allgetRegister(Register.PosAbs)
        
        for i in rawdata:
            data.append(toSignedInt(i))
        
        return data
    
    def allGetSpeed(self):
        """
        """
        data = []
        
        rawdata = self.allgetRegister(Register.Speed)
        
        for i in rawdata:
            data.append(i/Constant.SpsToSpeed)
            
        return data
    
    def allRun(self,speeds):
        """
        """
        command = [] 
                
        for s in speeds:
            ints = int(Constant.SpsToSpeed *s)
            ds = toPlusAndDir(ints)
            direction = ds[0]
            absspeed = toByteArrayWithLength(ds[1], RegisterSize(Register.Speed)) 
            command.append([Command.Run | direction, b for b in absspeed]) 
        
        self.runCommands(command)
        