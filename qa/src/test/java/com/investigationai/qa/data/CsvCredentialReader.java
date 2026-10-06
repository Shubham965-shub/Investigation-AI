package com.investigationai.qa.data;

import com.investigationai.qa.config.ConfigReader;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public final class CsvCredentialReader {
    private CsvCredentialReader() {
    }

    public static Object[][] readUsers() {
        String path = ConfigReader.get("usersCsvPath");
        InputStream input = CsvCredentialReader.class.getClassLoader().getResourceAsStream(path);
        if (input == null) {
            throw new IllegalStateException("Credential CSV was not found: " + path);
        }

        List<Object[]> users = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
            String line;
            boolean header = true;
            while ((line = reader.readLine()) != null) {
                if (header) {
                    header = false;
                    continue;
                }
                if (line.isBlank() || line.trim().startsWith("#")) {
                    continue;
                }
                String[] columns = line.split(",", -1);
                if (columns.length < 2 || columns[0].isBlank() || columns[1].isBlank()) {
                    throw new IllegalArgumentException("Each CSV row must contain username,password: " + line);
                }
                users.add(new Object[] {resolve(columns[0].trim()), resolve(columns[1].trim())});
            }
        } catch (IOException exception) {
            throw new IllegalStateException("Could not read credential CSV: " + path, exception);
        }
        if (users.isEmpty()) {
            throw new IllegalStateException("Credential CSV contains no users: " + path);
        }
        return users.toArray(new Object[0][]);
    }

    private static String resolve(String value) {
        if (value.startsWith("${") && value.endsWith("}")) {
            String variable = value.substring(2, value.length() - 1);
            String resolved = System.getenv(variable);
            if (resolved == null || resolved.isBlank()) {
                throw new IllegalStateException("Missing environment variable for CSV value: " + variable);
            }
            return resolved;
        }
        return value;
    }
}