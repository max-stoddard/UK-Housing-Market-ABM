package utilities;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

class BinnedDataDoubleTest {

    @TempDir
    Path tempDir;

    @Test
    void csvConstructorPreservesVariableWidthEdges() throws Exception {
        Path csvPath = tempDir.resolve("variable-age.csv");
        Files.writeString(csvPath,
                "# lower, upper, value\n"
                        + "16, 20, 0.05\n"
                        + "20, 25, 0.10\n"
                        + "25, 35, 0.20\n",
                StandardCharsets.UTF_8);

        BinnedDataDouble data = new BinnedDataDouble(csvPath.toString());

        assertAll(
                () -> assertEquals(16.0, data.getSupportLowerBound(), 1.0e-12),
                () -> assertEquals(35.0, data.getSupportUpperBound(), 1.0e-12),
                () -> assertEquals(16.0, data.getBinLowerEdge(0), 1.0e-12),
                () -> assertEquals(20.0, data.getBinUpperEdge(0), 1.0e-12),
                () -> assertEquals(4.0, data.getBinWidth(0), 1.0e-12),
                () -> assertEquals(22.5, data.getBinCenter(1), 1.0e-12),
                () -> assertEquals(10.0, data.getBinWidth(2), 1.0e-12)
        );
    }

    @Test
    void csvBackedGetBinAtUsesExplicitEdges() throws Exception {
        Path csvPath = tempDir.resolve("variable-age.csv");
        Files.writeString(csvPath,
                "# lower, upper, value\n"
                        + "16, 20, 1.0\n"
                        + "20, 25, 2.0\n"
                        + "25, 35, 3.0\n",
                StandardCharsets.UTF_8);

        BinnedDataDouble data = new BinnedDataDouble(csvPath.toString());

        assertAll(
                () -> assertEquals(1.0, data.getBinAt(16.0), 1.0e-12),
                () -> assertEquals(1.0, data.getBinAt(19.999), 1.0e-12),
                () -> assertEquals(2.0, data.getBinAt(20.0), 1.0e-12),
                () -> assertEquals(2.0, data.getBinAt(24.999), 1.0e-12),
                () -> assertEquals(3.0, data.getBinAt(25.0), 1.0e-12),
                () -> assertEquals(3.0, data.getBinAt(35.0), 1.0e-12),
                () -> assertEquals(1.0, data.getBinAt(10.0), 1.0e-12),
                () -> assertEquals(3.0, data.getBinAt(50.0), 1.0e-12)
        );
    }

    @Test
    void manualConstructorKeepsLegacyEqualWidthBehaviour() {
        BinnedDataDouble data = new BinnedDataDouble(15.0, 10.0);
        data.add(0.1);
        data.add(0.2);
        data.add(0.3);

        assertAll(
                () -> assertEquals(45.0, data.getSupportUpperBound(), 1.0e-12),
                () -> assertEquals(10.0, data.getBinWidth(), 1.0e-12),
                () -> assertEquals(10.0, data.getBinWidth(1), 1.0e-12),
                () -> assertEquals(25.0, data.getBinLowerEdge(1), 1.0e-12),
                () -> assertEquals(35.0, data.getBinUpperEdge(1), 1.0e-12),
                () -> assertEquals(30.0, data.getBinCenter(1), 1.0e-12),
                () -> assertEquals(0.2, data.getBinAt(25.0), 1.0e-12)
        );
    }

    @Test
    void csvWithEqualLowerEdgeSpacingKeepsLegacySingleWidthBehaviour() throws Exception {
        Path csvPath = tempDir.resolve("was-age8.csv");
        Files.writeString(csvPath,
                "# lower, upper, value\n"
                        + "15, 25, 1.0\n"
                        + "25, 35, 2.0\n"
                        + "35, 55, 3.0\n",
                StandardCharsets.UTF_8);

        BinnedDataDouble data = new BinnedDataDouble(csvPath.toString());

        assertAll(
                () -> assertEquals(45.0, data.getSupportUpperBound(), 1.0e-12),
                () -> assertEquals(10.0, data.getBinWidth(), 1.0e-12),
                () -> assertEquals(45.0, data.getBinUpperEdge(2), 1.0e-12),
                () -> assertEquals(3.0, data.getBinAt(35.0), 1.0e-12),
                () -> assertEquals(3.0, data.getBinAt(44.999), 1.0e-12)
        );
    }
}
