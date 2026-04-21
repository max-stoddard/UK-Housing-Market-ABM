package collectors;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MicroDataRecorderTest {

    @TempDir
    Path tempDir;

    @Test
    void writesNewMicroSnapshotFilesUsingExistingSemicolonFormat() throws Exception {
        MicroDataRecorder recorder = new MicroDataRecorder(tempDir.toString() + File.separator);

        recorder.openSingleRunSingleVariableFiles(1, false, false, false, false, false, true,
                false, true, false, true, false);
        recorder.timeStampSingleRunSingleVariableFiles(996, false, false, false, false, false, true,
                false, true, false, true, false);
        recorder.recordTotalDebt(996, 12345.67);
        recorder.recordHousingStatus(996, 2);
        recorder.recordConsumption(996, 890.12);
        recorder.finishRun(false, false, false, false, false, true, false, true,
                false, true, false);

        assertAll(
                () -> assertEquals("996; 12345.67",
                        Files.readString(tempDir.resolve("TotalDebt-run1.csv")).trim()),
                () -> assertEquals("996; 2",
                        Files.readString(tempDir.resolve("HousingStatus-run1.csv")).trim()),
                () -> assertEquals("996; 890.12",
                        Files.readString(tempDir.resolve("NonHousingConsumption-run1.csv")).trim())
        );
    }
}
