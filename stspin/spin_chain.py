from .constants import (
    Command,
    Constant,
    Register,
    Status,
)
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

from stspin.spin_device import SpinDevice

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
        self.commands = [Command.Nop] * self._total_devices
        self.datasize = [0] * self._total_devices

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

    def _completeCommands(self,data):
        """
        """
        maxlen = 1

        for cmd in data:
            if not(isinstance(cmd,int)):
                maxlen = max(len(cmd), maxlen)
        if maxlen >1:
            for i in range (self._total_devices):
                if (isinstance(data[i],int)):
                    n = maxlen - 1
                else:
                    n = maxlen - len(data[i])
                if n > 0:
                    data[i].append([0x00] * n)
           
        return transpose(data)       
                               
    def addCommand(self, data) -> None:
        """
        """
        position = data[0]
        command = data[1]

        self.commands[position] = command
        self.datasize[position] = len(data)-2
        
        if len(data) > 2:
            for i in range(2,len(data)):        
                self.commands[position].append(data[i])
                              
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
        response = [0]*self._total_devices
        
        for i in range(self._total_devices):
            
            if datalenght[i] == 0:
                response[i] = None
            
            else:
                response[i] = toInt(data[i][1:datalenght[i]+1])
                
        return response
                            
    def runCommands(self, data:List[List[int]]):
        """Write some bytes to all devices
        :data: List containing list of byte indexed by postiton in the chain
            MSB coming first.
        :return: List of responses, MSB first
        """        
        
        data_byte =[]
        responses = []

        datat = self._completeCommands(data)
        
        if len(datat[0]) != self._total_devices:
            pass

        for data_byte in datat:
            responses.append(self._pllwrite(data_byte))
        
        size = self.datasize
        self._resetCommands()
        rdata=self._getResponses(transpose(responses),size)
        
        return rdata
    
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
        
    def allGetRegister(self, register: int) -> int:
        """Fetches a register's contents and returns the current value

        :register: Register location to be accessed
        :returns: Value of specified register
        """
        command = []
        RegisterSize = Register.getSize(register)
        self.datasize = [RegisterSize] * self._total_devices
        
        command.append(Command.ParamGet | register)
        i=0
        for i in range(RegisterSize):
            command.append(Command.Nop)
        commands = [command] *self._total_devices

        response=self.runCommands(commands)
        
        return response

    def allSetRegister(self, register : int, values: List[int]) -> None:
        """
        """
        set_command = []
        RegisterSize = Register.getSize(register)
        cmd = Command.ParamSet | register

        for v in values:
            cmdline = []
            tobytes = toByteArrayWithLength(v, RegisterSize)
            cmdline.append(cmd)

            for i in range(RegisterSize):
                cmdline.append(tobytes[i])
            set_command.append(cmdline)

        self.runCommands(set_command)
        
    def allGetPosition(self):
        """
        """
        data = []
        rawdata = self.allGetRegister(Register.PosAbs)
        
        for i in rawdata:
            data.append(toSignedInt(i))
        
        return data

    def allGetMark(self):
        """
        """
        data = []
        rawdata = self.allGetRegister(Register.Mark)
        
        for i in rawdata:
            data.append(toSignedInt(i))
        
        return data

    def allSetPosition(self,positions: List[int]):
        """
        """
        self.allSetRegister(Register.PosAbs,positions)

    def allSetMark(self,positions: List[int]):
        """
        """
        self.allSetRegister(Register.Mark,positions)

    def allGetSpeed(self):
        """
        """
        data = []

        rawdata = self.allGetRegister(Register.Speed)
        dir = self.allGetStatus(Status.Dir)
        
        for i in rawdata:
            if not dir[i]:   # 0 is negative
                i = -i

            data.append(i/Constant.SpsToSpeed)
            
        return data
        
    def allGetStatus(self, statusmask) -> int:
        """
        """
        returndata = []

        stdatas = self.allGetRegister(Register.Status)

        for stdata in stdatas:
            returndata.append(stdata & statusmask)

        return returndata

    def allRun(self,speeds):

        """
        """
        command = []
        ds =[]
        #self.datasize = [Register.getSize(Register.Speed)]*self._total_devices
                
        for s in speeds:
            ints = int(Constant.SpsToSpeed *s)
            ds = toPlusAndDir(ints)
            bytelen = Register.getSize(Register.Speed)
            commandline = []
            commandline.append(Command.Run | ds[0])
            tobytes = toByteArrayWithLength(ds[1], bytelen)

            for i in range(bytelen):
                commandline.append(tobytes[i])

            command.append(commandline)
        
        self.runCommands(command)

    def isOneBusy(self):
        """
        """
        regvalues = self.allGetStatus(Status.NotBusy)
          
        cst = False
        for regvalue in regvalues:
            if regvalue == 0 :
                cst=True
                break

        return cst

        