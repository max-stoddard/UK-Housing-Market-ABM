package collectors;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RecorderCompatibilityTest {

    @Test
    void outputRunHeaderPreservesLegacyPrefixOrdering(@TempDir Path tempDir) throws IOException {
        Recorder recorder = new Recorder(tempDir.toString() + "/");

        recorder.openSingleRunFiles(1, true, 3);
        recorder.finishRun(false, true, true);

        List<String> actualColumns = splitHeader(readFirstLine(tempDir.resolve("Output-run1.csv")));
        List<String> expectedColumns = splitHeader(readResourceFirstLine(
                "uk-observability/baseline/Output-run1-header.csv"));

        assertTrue(actualColumns.size() >= expectedColumns.size());
        assertEquals(expectedColumns, actualColumns.subList(0, expectedColumns.size()));
    }

    @Test
    void qualityBandHeaderMatchesPreChangeFixture(@TempDir Path tempDir) throws IOException {
        Recorder recorder = new Recorder(tempDir.toString() + "/");

        recorder.openSingleRunFiles(1, true, 3);
        recorder.finishRun(false, true, true);

        List<String> actualColumns = splitHeader(readFirstLine(tempDir.resolve("QualityBandPrice-run1.csv")));
        List<String> expectedColumns = splitHeader(readResourceFirstLine(
                "uk-observability/baseline/QualityBandPrice-run1-header.csv"));

        assertEquals(expectedColumns, actualColumns);
    }

    @Test
    void legacySingleVariableMicroFilesMatchPreChangeFixtures(@TempDir Path tempDir) throws IOException {
        MicroDataRecorder recorder = new MicroDataRecorder(tempDir.toString() + "/");

        recorder.openSingleRunSingleVariableFiles(1,
                true, false, false, true, false, false, false, false, false, false, false);

        recorder.timeStampSingleRunSingleVariableFiles(995,
                true, false, false, true, false, false, false, false, false, false, false);
        recorder.recordHouseholdID(995, 99);
        recorder.recordBankBalance(995, 42.0);

        recorder.timeStampSingleRunSingleVariableFiles(996,
                true, false, false, true, false, false, false, false, false, false, false);
        recorder.recordHouseholdID(996, 101);
        recorder.recordHouseholdID(996, 202);
        recorder.recordBankBalance(996, 1234.5);
        recorder.recordBankBalance(996, 0.33);

        recorder.timeStampSingleRunSingleVariableFiles(1008,
                true, false, false, true, false, false, false, false, false, false, false);
        recorder.recordHouseholdID(1008, 303);
        recorder.recordBankBalance(1008, 987654.321);

        recorder.finishRun(true, false, false, true, false, false, false, false, false, false, false);

        assertEquals(
                readResourceLines("uk-observability/baseline/HouseholdID-run1.csv"),
                Files.readAllLines(tempDir.resolve("HouseholdID-run1.csv"), StandardCharsets.UTF_8));
        assertEquals(
                readResourceLines("uk-observability/baseline/BankBalance-run1.csv"),
                Files.readAllLines(tempDir.resolve("BankBalance-run1.csv"), StandardCharsets.UTF_8));
    }

    private static String readFirstLine(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        return lines.isEmpty() ? "" : lines.get(0);
    }

    private static String readResourceFirstLine(String resourcePath) throws IOException {
        List<String> lines = readResourceLines(resourcePath);
        return lines.isEmpty() ? "" : lines.get(0);
    }

    private static List<String> readResourceLines(String resourcePath) throws IOException {
        InputStream stream = RecorderCompatibilityTest.class.getClassLoader().getResourceAsStream(resourcePath);
        Objects.requireNonNull(stream, "Missing test resource: " + resourcePath);

        List<String> lines = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line = reader.readLine();
            while (line != null) {
                lines.add(line);
                line = reader.readLine();
            }
        }
        return lines;
    }

    private static List<String> splitHeader(String header) {
        List<String> columns = new ArrayList<>();
        for (String token : header.split(";")) {
            columns.add(token.trim());
        }
        return columns;
    }
}
